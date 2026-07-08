"""Verified requirement extraction for the Evidence Map.

The LLM proposes requirements with citation quotes over batches of one
document's chunks; each quote is verified verbatim against the exact chunk text
(same rules as services/verification.py). Only requirements with at least one
validated citation are persisted — weak evidence never enters the Evidence Map.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.ai import llm
from atip_api.config import Settings
from atip_api.errors import (
    DocumentNotReadyError,
    GenerationDisabledError,
    GenerationFailedError,
    NotFoundError,
)
from atip_api.models import Chunk, DocumentStatus, EvidenceCitation, EvidenceItem
from atip_api.repositories.chunks import ChunkRepository
from atip_api.repositories.documents import DocumentRepository
from atip_api.repositories.evidence import EvidenceRepository
from atip_api.repositories.workspaces import WorkspaceRepository
from atip_api.schemas.evidence import (
    EvidenceCitationRead,
    EvidenceExtractResponse,
    EvidenceItemRead,
    EvidenceItemUpdate,
    EvidenceMapExport,
)
from atip_api.services.evidence_prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from atip_api.services.rag import GENERATION_DISABLED_MESSAGE, GENERATION_FAILED_MESSAGE
from atip_api.services.verification import RetrievedSource, quote_supported

logger = logging.getLogger(__name__)

# chunks per LLM call; batches are processed in deterministic chunk_index order
_BATCH_SIZE = 12

_WS_RE = re.compile(r"\s+")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


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
        )
        for i, chunk in enumerate(chunks)
    ]


class EvidenceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repo = EvidenceRepository(session)
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def extract(self, document_id: uuid.UUID) -> EvidenceExtractResponse:
        """Extract requirements for one READY document.

        Re-extraction replaces the document's existing evidence items,
        including their reviewer-set status/risk.
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

        await self._repo.delete_by_document(document.id)
        await self._repo.add_all(items)
        await self._session.commit()

        return EvidenceExtractResponse(
            document_id=document.id,
            items=[_read(item, document.name) for item in items],
            requirements_seen=requirements_seen,
            requirements_dropped=requirements_dropped,
            citations_dropped=citations_dropped,
            warnings=warnings,
            model=self._settings.llm_model,
        )

    async def list_items(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID | None = None
    ) -> list[EvidenceItemRead]:
        if await self._workspaces.get(workspace_id) is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        rows = await self._repo.list_by_workspace(workspace_id, document_id)
        return [_read(item, document_name) for item, document_name in rows]

    async def update_item(self, item_id: uuid.UUID, patch: EvidenceItemUpdate) -> EvidenceItemRead:
        row = await self._repo.get(item_id)
        if row is None:
            raise NotFoundError(f"Evidence item {item_id} not found")
        item, document_name = row
        if patch.status is not None:
            item.status = patch.status
        if patch.risk is not None:
            item.risk = patch.risk
        await self._session.commit()
        await self._session.refresh(item)
        return _read(item, document_name)

    async def export(self, workspace_id: uuid.UUID) -> EvidenceMapExport:
        workspace = await self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        rows = await self._repo.list_by_workspace(workspace_id)
        return EvidenceMapExport(
            workspace_id=workspace_id,
            workspace_name=workspace.name,
            generated_at=datetime.now(UTC),
            items=[_read(item, document_name) for item, document_name in rows],
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
                f"- Status: {item.status} | Risk: {item.risk} | Clause: {clause}",
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
        lines.append("")
    if not export.items:
        lines.extend(["_No evidence items. Run extraction on a processed document._", ""])
    return "\n".join(lines)
