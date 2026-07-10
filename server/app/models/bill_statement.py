import datetime
import uuid

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillStatement(Base):
    """A biller's "statement ready" event, matched against the later payment transaction
    (CLAUDE.md §4/§10) — the pair is what makes the cash-flow calendar ("due before next
    paycheck") possible. ``account_id`` is the payment rail this biller is bound to (CLAUDE.md
    §2: each biller rides one account, so checking-side rules never double-count a card bill).
    """

    __tablename__ = "bill_statements"

    # F13: one bill per matched transaction. Partial, because "unmatched" is the normal state
    # and those NULLs must stay free to repeat. Declared here as well as in the migration so
    # the tests' `create_all` schema carries the invariant too, not just a migrated database.
    __table_args__ = (
        Index(
            "uq_bill_statements_matched_transaction_id",
            "matched_transaction_id",
            unique=True,
            postgresql_where=text("matched_transaction_id IS NOT NULL"),
        ),
    )

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
