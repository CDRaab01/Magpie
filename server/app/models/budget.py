import uuid
from datetime import date as date_

from sqlalchemy import BigInteger, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Budget(Base):
    """A monthly amount per category (CLAUDE.md §4). ``month`` is a first-of-month marker
    (e.g. 2026-07-01 = July 2026). ``user_id`` scopes each budget to its owner (F10) — before it
    existed, ``list_budgets`` returned every user's rows for the month, a cross-user leak the
    Budgets screen would have surfaced. Nullable in the schema only so the additive migration is
    safe against any pre-scoping orphan rows (which then match no user and stay invisible); the app
    always sets it, and the ownership filter is the read guard, mirroring the other domains.
    """

    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[date_] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
