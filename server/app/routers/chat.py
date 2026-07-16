import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.schemas.chat import ChatRequest, ChatResponse
from app.security import LedgerUser
from app.services.chat_service import answer_question
from app.services.ingest_service import make_llm_client

router = APIRouter(prefix="/chat", tags=["chat"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: Request, req: ChatRequest, current_user: LedgerUser, db: DbSession):
    """Ask a descriptive question about your money (ROADMAP #21). Answered from DB-derived
    aggregates only — never a raw transaction, never an email — read-only and descriptive-only
    (CLAUDE.md §6). A malformed turn returns 422; a missing local model returns 200 with a plain
    "chat isn't available" reply rather than an error.

    Rate-limited: this is the app's most expensive endpoint (a per-call local-LLM inference), so a
    per-client cap keeps a runaway client from saturating the one local model the whole app shares."""
    now = datetime.datetime.now(datetime.timezone.utc)
    error, reply = await answer_question(
        db,
        current_user.id,
        req.message,
        [m.model_dump() for m in req.history],
        llm_client=make_llm_client(settings.llm_chat_timeout_seconds),
        now=now,
    )
    if error is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error)
    return ChatResponse(reply=reply)
