import uuid
from collections.abc import Sequence
from typing import Any, Literal

from sqlalchemy import Select, case, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from atip_api.models import (
    Document,
    EvidenceCitation,
    EvidenceItem,
    EvidenceReviewEvent,
    EvidenceRisk,
    ReviewStatus,
)

QueueSort = Literal[
    "updated_desc", "updated_asc", "created_desc", "created_asc", "risk_desc", "risk_asc"
]

# UNRATED sorts below LOW so "highest risk first" surfaces rated items
_RISK_ORDER = case(
    (EvidenceItem.risk == EvidenceRisk.HIGH, 3),
    (EvidenceItem.risk == EvidenceRisk.MEDIUM, 2),
    (EvidenceItem.risk == EvidenceRisk.LOW, 1),
    else_=0,
)

_HAS_EVENTS = exists(
    select(EvidenceReviewEvent.id).where(EvidenceReviewEvent.evidence_item_id == EvidenceItem.id)
)


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_all(self, items: Sequence[EvidenceItem]) -> None:
        self._session.add_all(items)
        await self._session.flush()

    async def get(self, item_id: uuid.UUID) -> tuple[EvidenceItem, str] | None:
        row = (
            await self._session.execute(
                select(EvidenceItem, Document.name)
                .join(Document, EvidenceItem.document_id == Document.id)
                .options(selectinload(EvidenceItem.citations))
                .where(EvidenceItem.id == item_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        *,
        review_status: ReviewStatus | None = None,
        risk: EvidenceRisk | None = None,
        include_archived: bool = False,
    ) -> list[tuple[EvidenceItem, str]]:
        """Items with their document name, in stable citation-page order."""
        stmt = (
            select(EvidenceItem, Document.name)
            .join(Document, EvidenceItem.document_id == Document.id)
            .options(selectinload(EvidenceItem.citations))
            .where(EvidenceItem.workspace_id == workspace_id)
            .order_by(Document.name, EvidenceItem.created_at, EvidenceItem.id)
        )
        if document_id is not None:
            stmt = stmt.where(EvidenceItem.document_id == document_id)
        if review_status is not None:
            stmt = stmt.where(EvidenceItem.review_status == review_status)
        if risk is not None:
            stmt = stmt.where(EvidenceItem.risk == risk)
        if not include_archived:
            stmt = stmt.where(EvidenceItem.archived_at.is_(None))
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def query_queue(
        self,
        *,
        workspace_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        review_status: ReviewStatus | None,
        risk: EvidenceRisk | None,
        include_archived: bool,
        sort: QueueSort,
        limit: int,
        offset: int,
        workspace_ids: Sequence[uuid.UUID] | None = None,
    ) -> tuple[list[tuple[EvidenceItem, str, int]], int]:
        """Review-queue page of (item, document_name, citation_count) plus total.

        `workspace_ids` is the caller's tenant allow-list (None = unrestricted);
        it composes with the explicit `workspace_id` filter."""

        def filtered(stmt: Select[Any]) -> Select[Any]:
            if workspace_ids is not None:
                stmt = stmt.where(EvidenceItem.workspace_id.in_(workspace_ids))
            if workspace_id is not None:
                stmt = stmt.where(EvidenceItem.workspace_id == workspace_id)
            if document_id is not None:
                stmt = stmt.where(EvidenceItem.document_id == document_id)
            if review_status is not None:
                stmt = stmt.where(EvidenceItem.review_status == review_status)
            if risk is not None:
                stmt = stmt.where(EvidenceItem.risk == risk)
            if not include_archived:
                stmt = stmt.where(EvidenceItem.archived_at.is_(None))
            return stmt

        order_by = {
            "updated_desc": (EvidenceItem.updated_at.desc(),),
            "updated_asc": (EvidenceItem.updated_at.asc(),),
            "created_desc": (EvidenceItem.created_at.desc(),),
            "created_asc": (EvidenceItem.created_at.asc(),),
            "risk_desc": (_RISK_ORDER.desc(), EvidenceItem.updated_at.desc()),
            "risk_asc": (_RISK_ORDER.asc(), EvidenceItem.updated_at.desc()),
        }[sort]

        citation_count = (
            select(func.count(EvidenceCitation.id))
            .where(EvidenceCitation.evidence_item_id == EvidenceItem.id)
            .correlate(EvidenceItem)
            .scalar_subquery()
        )
        stmt = (
            filtered(
                select(EvidenceItem, Document.name, citation_count).join(
                    Document, EvidenceItem.document_id == Document.id
                )
            )
            .order_by(*order_by, EvidenceItem.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).all()

        total = (
            await self._session.execute(filtered(select(func.count()).select_from(EvidenceItem)))
        ).scalar_one()
        return [(row[0], row[1], row[2]) for row in rows], total

    async def add_event(self, event: EvidenceReviewEvent) -> None:
        self._session.add(event)
        await self._session.flush()

    async def list_events(self, item_id: uuid.UUID) -> list[EvidenceReviewEvent]:
        rows = (
            await self._session.execute(
                select(EvidenceReviewEvent)
                .where(EvidenceReviewEvent.evidence_item_id == item_id)
                .order_by(EvidenceReviewEvent.seq)
            )
        ).scalars()
        return list(rows)

    async def list_events_for_items(
        self, item_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[EvidenceReviewEvent]]:
        if not item_ids:
            return {}
        rows = (
            await self._session.execute(
                select(EvidenceReviewEvent)
                .where(EvidenceReviewEvent.evidence_item_id.in_(item_ids))
                .order_by(EvidenceReviewEvent.seq)
            )
        ).scalars()
        by_item: dict[uuid.UUID, list[EvidenceReviewEvent]] = {}
        for event in rows:
            by_item.setdefault(event.evidence_item_id, []).append(event)
        return by_item

    async def delete_unreviewed_by_document(self, document_id: uuid.UUID) -> None:
        """Remove items that were never reviewed (still NEW, zero audit events)."""
        await self._session.execute(
            delete(EvidenceItem).where(
                EvidenceItem.document_id == document_id,
                EvidenceItem.review_status == ReviewStatus.NEW,
                ~_HAS_EVENTS,
            )
        )
        await self._session.flush()

    async def list_reviewed_live_by_document(self, document_id: uuid.UUID) -> list[EvidenceItem]:
        """Live (non-archived) items that carry review state or audit history."""
        rows = (
            await self._session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.document_id == document_id,
                    EvidenceItem.archived_at.is_(None),
                    (EvidenceItem.review_status != ReviewStatus.NEW) | _HAS_EVENTS,
                )
            )
        ).scalars()
        return list(rows)
