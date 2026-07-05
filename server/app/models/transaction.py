import datetime
import uuid

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# "pending" | "posted" (CLAUDE.md §4/§10 — auth holds that never post get expired by a sweep).
TRANSACTION_STATUSES = ("pending", "posted")
# "spend" | "income" | "transfer" | "refund" (CLAUDE.md §2 — the accounting-semantics core:
# card payments are "transfer" pairs that net to zero via transfer_group; refunds are negative
# spend in the original category, never "income").
TRANSACTION_KINDS = ("spend", "income", "transfer", "refund")
# "auto" | "needs_review" | "confirmed" — what the review queue is keyed on.
REVIEW_STATES = ("auto", "needs_review", "confirmed")
# "email" | "csv" | "manual" — provenance of how a transaction entered the ledger.
TRANSACTION_SOURCES = ("email", "csv", "manual")


class Transaction(Base):
    """The signed ledger row (CLAUDE.md §4). Amounts are **integer cents, never floats**
    (CLAUDE.md invariant #11) — the ``app/ledger/`` module (Phase 2) is the only place that
    interprets sign/kind/transfer_group into totals; this model just stores the facts.
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    date: Mapped[datetime.date] = mapped_column(Date)
    posted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="posted")
    merchant_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_norm: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    # Pairs a transfer's two legs (e.g. card payment <-> checking outflow) so they net to zero;
    # NULL for every non-transfer transaction.
    transfer_group: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    review_state: Mapped[str] = mapped_column(String(20), default="needs_review")
    source: Mapped[str] = mapped_column(String(20))
    ingest_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingest_events.id", ondelete="SET NULL"), nullable=True
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
