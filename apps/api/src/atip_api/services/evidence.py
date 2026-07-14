"""Verified requirement extraction and review workflow for the Evidence Map.

Extraction: the LLM proposes requirements with citation quotes over batches of
one document's chunks; each quote is verified verbatim against the exact chunk
text (same rules as services/verification.py). Only requirements with at least
one validated citation are persisted — weak evidence never enters the map.

Review: evidence items carry a workflow `review_status` that changes only
through the audited state machine below; every mutation appends an append-only
`EvidenceReviewEvent`. Review data never touches citation provenance snapshots.
"""

import json
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from atip_api.ai import llm
from atip_api.config import Settings
from atip_api.errors import (
    DocumentNotReadyError,
    ExtractionInProgressError,
    GenerationDisabledError,
    GenerationFailedError,
    NotFoundError,
    ReviewTransitionError,
    StaleVersionError,
)
from atip_api.models import (
    ActorType,
    Chunk,
    DocumentStatus,
    EvidenceCitation,
    EvidenceItem,
    EvidenceReviewEvent,
    EvidenceRisk,
    ReviewAction,
    ReviewStatus,
)
from atip_api.repositories.chunks import ChunkRepository
from atip_api.repositories.documents import DocumentRepository
from atip_api.repositories.evidence import EvidenceRepository, QueueSort
from atip_api.repositories.workspaces import WorkspaceRepository
from atip_api.schemas.evidence import (
    EvidenceCitationRead,
    EvidenceExtractResponse,
    EvidenceItemDetail,
    EvidenceItemExport,
    EvidenceItemRead,
    EvidenceItemSummary,
    EvidenceItemUpdate,
    EvidenceMapExport,
    EvidenceQueuePage,
    ReviewEventRead,
    ReviewRequest,
    ReviewResponse,
)
from atip_api.services.evidence_prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from atip_api.services.rag import GENERATION_DISABLED_MESSAGE, GENERATION_FAILED_MESSAGE
from atip_api.services.verification import RetrievedSource, quote_supported

logger = logging.getLogger(__name__)

# chunks per LLM call; batches are processed in deterministic chunk_index order
_BATCH_SIZE = 12

_WS_RE = re.compile(r"\s+")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")

# review state machine (authoritative; documented in PHASE_5_HANDOFF.md)
_START_REVIEW_FROM = frozenset(
    {
        ReviewStatus.NEW,
        ReviewStatus.NEEDS_REVISION,
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
    }
)
_DECISIONS = {
    ReviewAction.APPROVE: ReviewStatus.APPROVED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
    ReviewAction.REQUEST_REVISION: ReviewStatus.NEEDS_REVISION,
}


def next_review_status(current: ReviewStatus, action: ReviewAction) -> ReviewStatus:
    """Pure transition function; raises ReviewTransitionError on invalid moves."""
    if action == ReviewAction.START_REVIEW:
        if current not in _START_REVIEW_FROM:
            raise ReviewTransitionError(f"Cannot start review from status {current}")
        return ReviewStatus.IN_REVIEW
    if action in _DECISIONS:
        if current != ReviewStatus.IN_REVIEW:
            raise ReviewTransitionError(
                f"Action {action} requires status IN_REVIEW (item is {current})"
            )
        return _DECISIONS[action]
    # COMMENT / SET_RISK never change the workflow status
    return current


class ProposedCitation(BaseModel):
    source: int
    quote: str = ""


class ProposedRequirement(BaseModel):
    text: str = ""
    citations: list[ProposedCitation] = Field(default_factory=list)


class ProposedRequirements(BaseModel):
    requirements: list[ProposedRequirement] = Field(default_factory=list)


@dataclass(frozen=True)
class _BatchOutcome:
    items: list[EvidenceItem]
    requirements_seen: int
    requirements_dropped: int
    citations_dropped: int
    warnings: list[str]


def parse_extraction_output(raw: str) -> ProposedRequirements | None:
    """Strict-JSON parse of the model output; None when unusable."""
    payload = _CODE_FENCE_RE.sub("", raw.strip())
    try:
        return ProposedRequirements.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        return None


def verify_batch(
    proposed: ProposedRequirements,
    sources: list[RetrievedSource],
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    seen_requirements: set[str],
) -> _BatchOutcome:
    """Turn proposed requirements into persistable items, keeping only
    quote-verified citations. Mutates `seen_requirements` for cross-batch dedupe."""
    by_index = {source.index: source for source in sources}
    items: list[EvidenceItem] = []
    dropped = 0
    citations_dropped = 0
    warnings: list[str] = []

    for requirement in proposed.requirements:
        text = _WS_RE.sub(" ", requirement.text).strip()
        if not text:
            dropped += 1
            continue
        key = text.casefold()
        if key in seen_requirements:
            continue

        citations: list[EvidenceCitation] = []
        cited_chunks: set[uuid.UUID] = set()
        for citation in requirement.citations:
            source = by_index.get(citation.source)
            if source is None:
                citations_dropped += 1
                warnings.append(
                    f"Dropped citation to nonexistent source [{citation.source}] "
                    f"for requirement: {text[:80]}"
                )
                continue
            if not quote_supported(citation.quote, source.text):
                citations_dropped += 1
                warnings.append(
                    f"Dropped unverifiable quote for source [{citation.source}] "
                    f"(requirement: {text[:80]})"
                )
                continue
            if source.chunk_id in cited_chunks:
                continue
            cited_chunks.add(source.chunk_id)
            citations.append(
                EvidenceCitation(
                    chunk_id=source.chunk_id,
                    clause_id=source.clause_id,
                    page_start=source.page_start,
                    page_end=source.page_end,
                    quote=_WS_RE.sub(" ", citation.quote).strip(),
                )
            )

        if not citations:
            dropped += 1
            warnings.append(f"Dropped requirement without verified evidence: {text[:80]}")
            continue

        seen_requirements.add(key)
        items.append(
            EvidenceItem(
                workspace_id=workspace_id,
                document_id=document_id,
                requirement_text=text,
                citations=citations,
            )
        )

    return _BatchOutcome(
        items=items,
        requirements_seen=len(proposed.requirements),
        requirements_dropped=dropped,
        citations_dropped=citations_dropped,
        warnings=warnings,
    )


def _sources_for(chunks: list[Chunk]) -> list[RetrievedSource]:
    return [
        RetrievedSource(
            index=i + 1,
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name="",  # single-document flow; name is in the prompt header
            clause_id=chunk.clause_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
            section_path=chunk.section_path,
        )
        for i, chunk in enumerate(chunks)
    ]


def _advisory_key(document_id: uuid.UUID) -> int:
    """Stable signed-64-bit advisory-lock key derived from the document id."""
    return int.from_bytes(document_id.bytes[:8], "big", signed=True)


_STALE_VERSION_MESSAGE = (
    "The evidence item was modified by someone else. Reload it and retry with the new version."
)


class EvidenceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repo = EvidenceRepository(session)
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def _commit_versioned(self) -> None:
        """Commit; a lost optimistic-lock race surfaces as 409, nothing written."""
        try:
            await self._session.commit()
        except StaleDataError as exc:
            await self._session.rollback()
            raise StaleVersionError(_STALE_VERSION_MESSAGE) from exc

    @staticmethod
    def _check_expected_version(item: EvidenceItem, expected_version: int | None) -> None:
        if expected_version is not None and expected_version != item.version:
            raise StaleVersionError(_STALE_VERSION_MESSAGE)

    async def extract(self, document_id: uuid.UUID) -> EvidenceExtractResponse:
        """Extract requirements for one READY document.

        Re-extraction lifecycle: items that were never reviewed (NEW, no audit
        events) are deleted; items with review state or history are archived —
        their citations and audit trail are preserved but they leave the queue.
        """
        client = llm.get_llm_client(self._settings)
        if client is None:
            raise GenerationDisabledError(GENERATION_DISABLED_MESSAGE)

        document = await self._documents.get_document(document_id)
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        if document.status != DocumentStatus.READY:
            raise DocumentNotReadyError(
                f"Document is {document.status}; evidence extraction needs a READY document"
            )

        # held until this transaction commits/rolls back; a parallel extraction
        # of the same document would interleave archive/delete/insert steps
        locked = await self._session.scalar(
            select(func.pg_try_advisory_xact_lock(_advisory_key(document_id)))
        )
        if not locked:
            raise ExtractionInProgressError(
                "An extraction is already running for this document. Try again when it finishes."
            )

        chunks = list(await self._chunks.list_by_document(document_id))
        items: list[EvidenceItem] = []
        warnings: list[str] = []
        seen: set[str] = set()
        requirements_seen = 0
        requirements_dropped = 0
        citations_dropped = 0

        for start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[start : start + _BATCH_SIZE]
            sources = _sources_for(batch)
            parts: list[str] = []
            try:
                async for delta in client.stream(
                    system=EXTRACTION_SYSTEM_PROMPT,
                    user=build_extraction_prompt(document.name, sources),
                ):
                    parts.append(delta)
            except Exception as exc:
                logger.exception("LLM extraction failed")
                raise GenerationFailedError(GENERATION_FAILED_MESSAGE) from exc

            proposed = parse_extraction_output("".join(parts))
            if proposed is None:
                warnings.append(
                    f"Model output for chunks {batch[0].chunk_index}-{batch[-1].chunk_index} "
                    "was not valid JSON and was skipped."
                )
                continue
            outcome = verify_batch(
                proposed,
                sources,
                workspace_id=document.workspace_id,
                document_id=document.id,
                seen_requirements=seen,
            )
            items.extend(outcome.items)
            requirements_seen += outcome.requirements_seen
            requirements_dropped += outcome.requirements_dropped
            citations_dropped += outcome.citations_dropped
            warnings.extend(outcome.warnings)

        if not chunks:
            warnings.append("Document has no chunks; nothing to extract.")

        items_archived = await self._archive_reviewed(document.id)
        await self._repo.delete_unreviewed_by_document(document.id)
        await self._repo.add_all(items)
        await self._session.commit()

        if items_archived:
            warnings.append(
                f"{items_archived} previously reviewed item(s) were archived, not deleted; "
                "their review history is preserved."
            )

        return EvidenceExtractResponse(
            document_id=document.id,
            items=[_read(item, document.name) for item in items],
            requirements_seen=requirements_seen,
            requirements_dropped=requirements_dropped,
            citations_dropped=citations_dropped,
            items_archived=items_archived,
            warnings=warnings,
            model=self._settings.llm_model,
        )

    async def _archive_reviewed(self, document_id: uuid.UUID) -> int:
        """Archive live items that carry review state/history; audit each one."""
        reviewed = await self._repo.list_reviewed_live_by_document(document_id)
        now = datetime.now(UTC)
        for item in reviewed:
            item.archived_at = now
            await self._repo.add_event(
                EvidenceReviewEvent(
                    evidence_item_id=item.id,
                    action=ReviewAction.EXTRACTION_ARCHIVED,
                    previous_status=item.review_status,
                    next_status=item.review_status,
                    previous_risk=item.risk,
                    next_risk=item.risk,
                    comment="Archived because the document was re-extracted.",
                    actor_name="system",
                    actor_type=ActorType.SYSTEM,
                )
            )
        return len(reviewed)

    async def list_items(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID | None = None
    ) -> list[EvidenceItemRead]:
        if await self._workspaces.get(workspace_id) is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        rows = await self._repo.list_by_workspace(workspace_id, document_id)
        return [_read(item, document_name) for item, document_name in rows]

    async def queue(
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
    ) -> EvidenceQueuePage:
        rows, total = await self._repo.query_queue(
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            document_id=document_id,
            review_status=review_status,
            risk=risk,
            include_archived=include_archived,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return EvidenceQueuePage(
            items=[
                EvidenceItemSummary(
                    id=item.id,
                    workspace_id=item.workspace_id,
                    document_id=item.document_id,
                    document_name=document_name,
                    requirement_text=item.requirement_text,
                    status=item.status,
                    risk=item.risk,
                    review_status=item.review_status,
                    citation_count=citation_count,
                    version=item.version,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item, document_name, citation_count in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def detail(self, item_id: uuid.UUID) -> EvidenceItemDetail:
        row = await self._repo.get(item_id)
        if row is None:
            raise NotFoundError(f"Evidence item {item_id} not found")
        item, document_name = row
        events = await self._repo.list_events(item_id)
        base = _read(item, document_name)
        return EvidenceItemDetail(
            **base.model_dump(),
            event_count=len(events),
            last_event=ReviewEventRead.model_validate(events[-1]) if events else None,
        )

    async def review(self, item_id: uuid.UUID, request: ReviewRequest) -> ReviewResponse:
        row = await self._repo.get(item_id)
        if row is None:
            raise NotFoundError(f"Evidence item {item_id} not found")
        item, document_name = row
        if item.archived_at is not None:
            raise ReviewTransitionError(
                "This item was archived by a re-extraction and is read-only"
            )
        self._check_expected_version(item, request.expected_version)

        previous_status = item.review_status
        previous_risk = item.risk
        next_status = next_review_status(previous_status, ReviewAction(request.action))

        item.review_status = next_status
        if request.action == ReviewAction.SET_RISK and request.risk is not None:
            item.risk = request.risk

        event = EvidenceReviewEvent(
            evidence_item_id=item.id,
            action=ReviewAction(request.action),
            previous_status=previous_status,
            next_status=next_status,
            previous_risk=previous_risk,
            next_risk=item.risk,
            comment=request.comment,
            actor_name=request.actor_name,
            actor_type=request.actor_type,
        )
        await self._repo.add_event(event)
        await self._commit_versioned()
        await self._session.refresh(item)
        await self._session.refresh(event)
        return ReviewResponse(
            item=_read(item, document_name), event=ReviewEventRead.model_validate(event)
        )

    async def history(self, item_id: uuid.UUID) -> list[ReviewEventRead]:
        if await self._repo.get(item_id) is None:
            raise NotFoundError(f"Evidence item {item_id} not found")
        events = await self._repo.list_events(item_id)
        return [ReviewEventRead.model_validate(event) for event in events]

    async def update_item(self, item_id: uuid.UUID, patch: EvidenceItemUpdate) -> EvidenceItemRead:
        """Inline compliance-status/risk edits (Phase 4 table). Audited: each
        changed field appends a review event; review_status is untouchable here."""
        row = await self._repo.get(item_id)
        if row is None:
            raise NotFoundError(f"Evidence item {item_id} not found")
        item, document_name = row
        self._check_expected_version(item, patch.expected_version)

        if patch.status is not None and patch.status != item.status:
            previous = item.status
            item.status = patch.status
            await self._repo.add_event(
                EvidenceReviewEvent(
                    evidence_item_id=item.id,
                    action=ReviewAction.SET_STATUS,
                    previous_status=item.review_status,
                    next_status=item.review_status,
                    previous_risk=item.risk,
                    next_risk=item.risk,
                    actor_name=patch.actor_name,
                    actor_type=ActorType.HUMAN,
                    extra={"field": "status", "previous": previous, "next": patch.status},
                )
            )
        if patch.risk is not None and patch.risk != item.risk:
            previous_risk = item.risk
            item.risk = patch.risk
            await self._repo.add_event(
                EvidenceReviewEvent(
                    evidence_item_id=item.id,
                    action=ReviewAction.SET_RISK,
                    previous_status=item.review_status,
                    next_status=item.review_status,
                    previous_risk=previous_risk,
                    next_risk=patch.risk,
                    actor_name=patch.actor_name,
                    actor_type=ActorType.HUMAN,
                )
            )
        await self._commit_versioned()
        await self._session.refresh(item)
        return _read(item, document_name)

    async def export(
        self,
        workspace_id: uuid.UUID,
        *,
        document_id: uuid.UUID | None = None,
        review_status: ReviewStatus | None = None,
        risk: EvidenceRisk | None = None,
        include_history: bool = False,
    ) -> EvidenceMapExport:
        workspace = await self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        rows = await self._repo.list_by_workspace(
            workspace_id, document_id, review_status=review_status, risk=risk
        )
        history: dict[uuid.UUID, list[EvidenceReviewEvent]] = {}
        if include_history:
            history = await self._repo.list_events_for_items([item.id for item, _ in rows])
        return EvidenceMapExport(
            workspace_id=workspace_id,
            workspace_name=workspace.name,
            generated_at=datetime.now(UTC),
            include_history=include_history,
            items=[
                EvidenceItemExport(
                    **_read(item, document_name).model_dump(),
                    history=(
                        [ReviewEventRead.model_validate(e) for e in history.get(item.id, [])]
                        if include_history
                        else None
                    ),
                )
                for item, document_name in rows
            ],
        )


def _read(item: EvidenceItem, document_name: str) -> EvidenceItemRead:
    return EvidenceItemRead(
        id=item.id,
        workspace_id=item.workspace_id,
        document_id=item.document_id,
        document_name=document_name,
        requirement_text=item.requirement_text,
        status=item.status,
        risk=item.risk,
        review_status=item.review_status,
        archived_at=item.archived_at,
        version=item.version,
        citations=[EvidenceCitationRead.model_validate(citation) for citation in item.citations],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def export_markdown(export: EvidenceMapExport) -> str:
    """Render the Evidence Map as a self-contained Markdown report."""
    lines = [
        f"# Evidence Map — {export.workspace_name}",
        "",
        f"Generated: {export.generated_at.isoformat()}",
        f"Items: {len(export.items)}",
        "",
    ]
    current_document: str | None = None
    for index, item in enumerate(export.items, start=1):
        if item.document_name != current_document:
            current_document = item.document_name
            lines.extend([f"## {current_document}", ""])
        clause_ids = sorted({c.clause_id for c in item.citations if c.clause_id})
        clause = ", ".join(clause_ids) if clause_ids else "—"
        lines.extend(
            [
                f"### {index}. {item.requirement_text}",
                "",
                f"- Status: {item.status} | Risk: {item.risk} | Review: {item.review_status} "
                f"| Clause: {clause}",
            ]
        )
        for citation in item.citations:
            pages = (
                f"p. {citation.page_start}"
                if citation.page_start == citation.page_end
                else f"pp. {citation.page_start}-{citation.page_end}"
            )
            clause_part = f"{citation.clause_id}, " if citation.clause_id else ""
            lines.append(f'- Evidence ({clause_part}{pages}): "{citation.quote}"')
        if item.history:
            lines.append("- Review history:")
            for event in item.history:
                detail = f" — {event.comment}" if event.comment else ""
                transition = (
                    f" ({event.previous_status} → {event.next_status})"
                    if event.previous_status != event.next_status
                    else ""
                )
                lines.append(
                    f"  - {event.created_at.isoformat()} {event.action} "
                    f"by {event.actor_name}{transition}{detail}"
                )
        lines.append("")
    if not export.items:
        lines.extend(["_No evidence items. Run extraction on a processed document._", ""])
    return "\n".join(lines)
