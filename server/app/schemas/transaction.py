import datetime
import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.ledger.classify import TRANSACTION_KINDS
from app.models.transaction import TRANSACTION_STATUSES


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    amount: int  # signed integer cents — CLAUDE.md invariant, never a float
    currency: str = "USD"
    date: datetime.date
    status: str = "posted"
    merchant_raw: str | None = None
    category_id: uuid.UUID | None = None
    kind: str
    # source/review_state are NOT client-settable: the service always stamps manual entries
    # as source="manual", review_state="confirmed" — there's no draft state to review here
    # (unlike email/CSV-ingested transactions, Phase 3/4).

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, v: str) -> str:
        if v not in TRANSACTION_KINDS:
            raise ValueError(f"kind must be one of {TRANSACTION_KINDS}")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in TRANSACTION_STATUSES:
            raise ValueError(f"status must be one of {TRANSACTION_STATUSES}")
        return v

    @field_validator("currency")
    @classmethod
    def currency_valid(cls, v: str) -> str:
        if len(v) != 3:
            raise ValueError("currency must be a 3-letter code")
        return v.upper()


class TransactionUpdate(BaseModel):
    # None = leave untouched. There is no "clear category" affordance yet (no use case for
    # it in Phase 2 — every transaction here is manually entered, already categorized or not).
    category_id: uuid.UUID | None = None
    merchant_raw: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    amount: int
    currency: str
    date: datetime.date
    status: str
    merchant_raw: str | None
    merchant_norm: str | None
    category_id: uuid.UUID | None
    kind: str
    transfer_group: str | None
    review_state: str
    source: str
    created_at: datetime.datetime


class MonthlySummaryOut(BaseModel):
    year: int
    month: int
    income_cents: int
    spend_cents: int
    net_cents: int
