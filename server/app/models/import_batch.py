import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportBatch(Base):
    """One CSV/OFX reconciliation run (CLAUDE.md §4, §9). Row counts are the operator-facing
    summary of what an import did — created/matched/skipped, not just "success"."""

    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    institution: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
