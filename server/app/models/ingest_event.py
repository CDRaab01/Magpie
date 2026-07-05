import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# "created" | "duplicate" | "unparsed" (CLAUDE.md §10, ARCHITECTURE.md ingestion pipeline).
# An "unparsed" outcome is the pipeline's worst silent-failure mode — surfaced via an operator
# view + an ntfy alert on backlog growth, not just logged and forgotten.
INGEST_OUTCOMES = ("created", "duplicate", "unparsed")


class IngestEvent(Base):
    """Raw provenance for every email-derived event (CLAUDE.md §4, §9). Kept even for unparsed/
    duplicate outcomes with the raw payload itself, so a fixed parser can replay history —
    a bad parse is recoverable, never permanent.
    """

    __tablename__ = "ingest_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    # RFC 5322 Message-ID header — the dedupe key alongside payload_hash.
    message_id: Mapped[str] = mapped_column(String(998), unique=True, index=True)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    parser: Mapped[str] = mapped_column(String(50))
    parse_version: Mapped[str] = mapped_column(String(20))
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(20))
    raw_payload: Mapped[str] = mapped_column(Text)
