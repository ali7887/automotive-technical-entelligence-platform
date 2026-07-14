import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import WorkspaceViewerDep
from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.ratelimit import rate_limited
from atip_api.schemas.rag import AskRequest, AskResponse
from atip_api.services.rag import RAGService

router = APIRouter(prefix="/api", tags=["rag"])

# /ask and /chat share one budget: both trigger retrieval + LLM generation
_ASK_LIMIT = rate_limited("ask", lambda settings: settings.rate_limit_ask_per_minute)


def get_rag_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RAGService:
    return RAGService(session, get_settings())


ServiceDep = Annotated[RAGService, Depends(get_rag_service)]


@router.post(
    "/workspaces/{workspace_id}/ask", response_model=AskResponse, dependencies=[_ASK_LIMIT]
)
async def ask_workspace(
    access: WorkspaceViewerDep, request: AskRequest, service: ServiceDep
) -> AskResponse:
    """Verified RAG: hybrid retrieval + LLM answer checked against the retrieved chunks."""
    return await service.ask(access.workspace.id, request)


def _sse(event: str, payload: BaseModel) -> str:
    # model_dump_json emits a single line, as SSE `data:` requires
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


async def _sse_stream(
    service: RAGService, workspace_id: uuid.UUID, request: AskRequest
) -> AsyncIterator[str]:
    async for event, payload in service.stream_events(workspace_id, request):
        yield _sse(event, payload)


@router.get("/workspaces/{workspace_id}/chat", dependencies=[_ASK_LIMIT])
async def chat_workspace(
    access: WorkspaceViewerDep,
    service: ServiceDep,
    question: Annotated[str, Query(min_length=1, max_length=500)],
    document_id: Annotated[uuid.UUID | None, Query()] = None,
    top_k: Annotated[int, Query(ge=1, le=20)] = 8,
) -> StreamingResponse:
    """Verified RAG over SSE: `sources`, then `token`*, then `final` — or `error`.

    Auth: EventSource sends the session cookie same-origin, so this GET is
    protected exactly like the JSON routes. Streamed tokens are the unverified
    draft; the `final` event carries the verified answer and citations and
    must replace the streamed text.
    """
    request = AskRequest(question=question, document_id=document_id, top_k=top_k)
    return StreamingResponse(
        _sse_stream(service, access.workspace.id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
