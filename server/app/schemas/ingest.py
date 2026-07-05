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
