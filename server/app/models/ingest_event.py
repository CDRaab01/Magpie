import datetime
import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# "created" | "duplicate" | "unparsed" (CLAUDE.md §10, ARCHITECTURE.md ingestion pipeline).
# An "unparsed" outcome is the pipeline's worst silent-failure mode — surfaced via an operator
# view + an ntfy alert on backlog growth, not just logged and forgotten.
INGEST_OUTCOMES = ("created", "duplicate", "unparsed")


class IngestEvent(Base):
    """Raw provenance for every email-derived event (CLAUDE.md §4, §9). Kept even for unparsed/
    duplicate outcomes with the raw payload hash, so a fixed parser can replay history —
    a bad parse is recoverable, never permanent.
    """

    __tablename__ = "ingest_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # RFC 5322 Message-ID header — the dedupe key alongside payload_hash.
    message_id: Mapped[str] = mapped_column(String(998), unique=True, index=True)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    parser: Mapped[str] = mapped_column(String(50))
    parse_version: Mapped[str] = mapped_column(String(20))
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(20))
