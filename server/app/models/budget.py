import uuid
from datetime import date as date_

from sqlalchemy import BigInteger, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Budget(Base):
    """A monthly amount per category (CLAUDE.md §4). ``month`` is a first-of-month marker
    (e.g. 2026-07-01 = July 2026). Single-user in practice today — see the household-sharing
    non-goal in ROADMAP.md; add a user_id column when that lands rather than before.
    """

    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[date_] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
