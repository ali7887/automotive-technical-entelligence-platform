"""Verified RAG orchestration: retrieve -> generate -> verify.

The LLM only ever sees retrieved chunks; its output is verified offline against
those exact chunks (services/verification.py) before anything is returned.
Retrieval happens before any streaming starts so the DB session is not needed
while tokens are in flight.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.ai import llm
from atip_api.config import Settings
from atip_api.errors import AppError, GenerationDisabledError, GenerationFailedError
from atip_api.schemas.rag import (
    AnswerVerification,
    AskRequest,
    AskResponse,
    Citation,
    RetrievedSourceRead,
    SourcesEvent,
    StreamErrorEvent,
    TokenEvent,
)
from atip_api.schemas.search import SearchRequest
from atip_api.services.rag_prompts import SYSTEM_PROMPT, build_user_prompt
from atip_api.services.retrieval import SearchService
from atip_api.services.verification import (
    CLAIMS_SENTINEL,
    NOT_FOUND_ANSWER,
    RetrievedSource,
    VerifiedAnswer,
    parse_llm_output,
    verify_answer,
)

logger = logging.getLogger(__name__)

GENERATION_DISABLED_MESSAGE = (
    "Answer generation is disabled because no OPENAI_API_KEY is configured. "
    "Keyword and hybrid search remain available."
)
GENERATION_FAILED_MESSAGE = "The language model request failed. Please try again."


@dataclass(frozen=True)
class _Retrieval:
    sources: list[RetrievedSource]
    semantic_used: bool


class RAGService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._settings = settings
        self._search = SearchService(session, settings)

    async def ask(self, workspace_id: uuid.UUID, request: AskRequest) -> AskResponse:
        """Non-streaming verified answer; raises typed AppErrors."""
        client = llm.get_llm_client(self._settings)
        if client is None:
            raise GenerationDisabledError(GENERATION_DISABLED_MESSAGE)
        retrieval = await self._retrieve(workspace_id, request)
        if not retrieval.sources:
            return self._no_sources_response(workspace_id, request, retrieval)
        parts: list[str] = []
        try:
            async for delta in client.stream(
                system=SYSTEM_PROMPT, user=build_user_prompt(retrieval.sources, request.question)
            ):
                parts.append(delta)
        except Exception as exc:
            logger.exception("LLM generation failed")
            raise GenerationFailedError(GENERATION_FAILED_MESSAGE) from exc
        return self._finalize(workspace_id, request, retrieval, "".join(parts))

    async def stream_events(
        self, workspace_id: uuid.UUID, request: AskRequest
    ) -> AsyncIterator[tuple[str, BaseModel]]:
        """SSE flow: `sources`, then `token`*, then `final` — or `error`.

        Streamed tokens are the unverified draft; clients must replace them with
        the verified answer carried by the `final` event.
        """
        client = llm.get_llm_client(self._settings)
        if client is None:
            yield ("error", StreamErrorEvent(code="generation_disabled",
                                             message=GENERATION_DISABLED_MESSAGE))
            return
        try:
            retrieval = await self._retrieve(workspace_id, request)
        except AppError as exc:
            yield ("error", StreamErrorEvent(code=exc.code, message=exc.message))
            return

        yield ("sources", SourcesEvent(sources=_sources_read(retrieval.sources)))
        if not retrieval.sources:
            yield ("final", self._no_sources_response(workspace_id, request, retrieval))
            return

        raw = ""
        emitted = 0
        answer_done = False
        # hold back a sentinel-sized tail so the claims block never leaks into tokens
        holdback = len(CLAIMS_SENTINEL) - 1
        try:
            async for delta in client.stream(
                system=SYSTEM_PROMPT, user=build_user_prompt(retrieval.sources, request.question)
            ):
                raw += delta
                if answer_done:
                    continue
                sentinel_at = raw.find(CLAIMS_SENTINEL)
                if sentinel_at != -1:
                    answer_done = True
                    visible_end = sentinel_at
                else:
                    visible_end = max(emitted, len(raw) - holdback)
                if visible_end > emitted:
                    yield ("token", TokenEvent(text=raw[emitted:visible_end]))
                    emitted = visible_end
        except Exception:
            logger.exception("LLM generation failed mid-stream")
            yield ("error", StreamErrorEvent(code="generation_failed",
                                             message=GENERATION_FAILED_MESSAGE))
            return

        yield ("final", self._finalize(workspace_id, request, retrieval, raw))

    async def _retrieve(self, workspace_id: uuid.UUID, request: AskRequest) -> _Retrieval:
        search = await self._search.search(
            workspace_id,
            SearchRequest(
                query=request.question, document_id=request.document_id, top_k=request.top_k
            ),
        )
        sources = [
            RetrievedSource(
                index=i + 1,
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_name=result.document_name,
                clause_id=result.clause_id,
                page_start=result.page_start,
                page_end=result.page_end,
                text=result.text,
                section_path=result.section_path,
            )
            for i, result in enumerate(search.results)
        ]
        return _Retrieval(sources=sources, semantic_used=search.semantic_used)

    def _finalize(
        self,
        workspace_id: uuid.UUID,
        request: AskRequest,
        retrieval: _Retrieval,
        raw: str,
    ) -> AskResponse:
        verified = verify_answer(parse_llm_output(raw), retrieval.sources)
        return self._response(workspace_id, request, retrieval, verified)

    def _no_sources_response(
        self, workspace_id: uuid.UUID, request: AskRequest, retrieval: _Retrieval
    ) -> AskResponse:
        verified = VerifiedAnswer(
            answer_md=NOT_FOUND_ANSWER,
            not_found=True,
            confidence=None,
            status="not_found",
            citations=[],
            claims_total=0,
            claims_validated=0,
            citations_dropped=0,
            warnings=["No matching chunks were retrieved for this question."],
        )
        return self._response(workspace_id, request, retrieval, verified)

    def _response(
        self,
        workspace_id: uuid.UUID,
        request: AskRequest,
        retrieval: _Retrieval,
        verified: VerifiedAnswer,
    ) -> AskResponse:
        return AskResponse(
            question=request.question,
            workspace_id=workspace_id,
            document_id=request.document_id,
            answer_md=verified.answer_md,
            not_found=verified.not_found,
            confidence=verified.confidence,
            citations=[
                Citation(
                    citation_id=citation.citation_id,
                    postgres_chunk_id=citation.source.chunk_id,
                    document_id=citation.source.document_id,
                    document_name=citation.source.document_name,
                    clause_id=citation.source.clause_id,
                    page_start=citation.source.page_start,
                    page_end=citation.source.page_end,
                    source_text_snippet=citation.snippet,
                    status=citation.status,
                )
                for citation in verified.citations
            ],
            verification=AnswerVerification(
                status=verified.status,
                claims_total=verified.claims_total,
                claims_validated=verified.claims_validated,
                citations_dropped=verified.citations_dropped,
                warnings=verified.warnings,
            ),
            sources=_sources_read(retrieval.sources),
            semantic_used=retrieval.semantic_used,
            model=self._settings.llm_model,
        )


def _sources_read(sources: list[RetrievedSource]) -> list[RetrievedSourceRead]:
    return [
        RetrievedSourceRead(
            index=source.index,
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_name=source.document_name,
            clause_id=source.clause_id,
            page_start=source.page_start,
            page_end=source.page_end,
        )
        for source in sources
    ]
