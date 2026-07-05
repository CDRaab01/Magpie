import datetime
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# "recurring_income" | "recurring_bill" | "transfer_match" | "merchant_category"
# (CLAUDE.md §5 — the rules engine's evaluation order runs these before any AI suggestion).
RULE_TYPES = ("recurring_income", "recurring_bill", "transfer_match", "merchant_category")


class Rule(Base):
    """A deterministic matching rule (CLAUDE.md §5) — ``app/rules/`` (Phase 2+) is the pure
    module that evaluates these; this model just stores them. ``cadence``/``amount_band`` are
    JSON since different rule types need different shapes (e.g. cadence: {"kind": "monthly",
    "day": 15, "slack_days": 5}; amount_band: {"pct": 0.2} for a rolling-median tolerance).
    """

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30))
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Normalized merchant-name pattern — the rule's identity key.
    matcher: Mapped[str] = mapped_column(String(255))
    cadence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    amount_band: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    last_matched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
