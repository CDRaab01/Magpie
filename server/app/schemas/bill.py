import datetime
import uuid

from pydantic import BaseModel


class BillStatementCreate(BaseModel):
    biller: str
    account_id: uuid.UUID
    amount_due: int
    due_date: datetime.date
    issued_at: datetime.datetime | None = None


class BillStatementOut(BaseModel):
    id: uuid.UUID
    biller: str
    account_id: uuid.UUID
    amount_due: int
    due_date: datetime.date
    issued_at: datetime.datetime
    matched_transaction_id: uuid.UUID | None
    # Computed at read time (CLAUDE.md's cash-flow calendar needs "is this missing" as a
    # first-class fact, not something the client re-derives from today's date itself).
    is_missing: bool
