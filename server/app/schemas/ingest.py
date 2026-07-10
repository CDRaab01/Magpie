import datetime
import uuid

from pydantic import BaseModel


class IngestEventOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID | None
    message_id: str
    received_at: datetime.datetime
    parser: str
    parse_version: str
    outcome: str


class IngestPollResultOut(BaseModel):
    fetched: int
    created: int
    duplicate: int
    unparsed: int


class ReplayEventOut(BaseModel):
    event_id: uuid.UUID
    message_id: str
    action: str  # "filed" | "duplicate" | "still_unparsed" | "skipped"
    reason: str
    amount_cents: int | None = None
    merchant: str | None = None
    txn_date: datetime.date | None = None


class ReplayResultOut(BaseModel):
    dry_run: bool
    examined: int
    filed: int
    duplicate: int
    still_unparsed: int
    skipped: int
    events: list[ReplayEventOut]
