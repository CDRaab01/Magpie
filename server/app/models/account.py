import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# "card" | "depository" (CLAUDE.md §4) — the accounting-semantics split that makes transfer
# detection possible (a card payment is an outflow from a depository account matched to an
# inflow on a card account). Plain string column, validated at the schema layer — the suite's
# convention for values that shouldn't need a migration to extend.
ACCOUNT_TYPES = ("card", "depository")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    institution: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(20))
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
