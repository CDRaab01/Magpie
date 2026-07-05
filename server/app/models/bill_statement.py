import datetime
import uuid

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillStatement(Base):
    """A biller's "statement ready" event, matched against the later payment transaction
    (CLAUDE.md §4/§10) — the pair is what makes the cash-flow calendar ("due before next
    paycheck") possible. ``account_id`` is the payment rail this biller is bound to (CLAUDE.md
    §2: each biller rides one account, so checking-side rules never double-count a card bill).
    """

    __tablename__ = "bill_statements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    biller: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    amount_due: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[datetime.date] = mapped_column(Date)
    issued_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    # NULL until the matching payment posts.
    matched_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
