import uuid
from datetime import date as date_

from sqlalchemy import BigInteger, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StatementCheckpoint(Base):
    """A balance anchor from a CSV/statement import (CLAUDE.md §2/§9) — the
    ledger-vs-statement delta computed from these is the app's honesty meter and the input
    to the v1 statement-parity acceptance gate."""

    __tablename__ = "statement_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    statement_date: Mapped[date_] = mapped_column(Date)
    stated_balance: Mapped[int] = mapped_column(BigInteger)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
