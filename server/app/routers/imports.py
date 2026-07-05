import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.schemas.imports import ImportSummaryOut
from app.security import CurrentUser
from app.services.import_service import import_csv

router = APIRouter(prefix="/imports", tags=["imports"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/csv", response_model=ImportSummaryOut)
@limiter.limit("10/minute")
async def import_csv_endpoint(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    account_id: Annotated[uuid.UUID, Form()],
    institution: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    content = await file.read()
    return await import_csv(db, current_user.id, account_id, institution, content)
