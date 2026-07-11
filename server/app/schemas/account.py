import uuid
from datetime import date as date_

from pydantic import BaseModel, field_validator

from app.models.account import ACCOUNT_TYPES


class AccountCreate(BaseModel):
    name: str
    institution: str
    type: str
    last4: str | None = None

    @field_validator("type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in ACCOUNT_TYPES:
            raise ValueError(f"type must be one of {ACCOUNT_TYPES}")
        return v

    @field_validator("last4")
    @classmethod
    def last4_valid(cls, v: str | None) -> str | None:
        if v is not None and (len(v) != 4 or not v.isdigit()):
            raise ValueError("last4 must be exactly 4 digits")
        return v


class AccountUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    institution: str
    type: str
    last4: str | None
    active: bool
    # Computed, not stored — app/ledger/balances.py. balance_delta_cents is None until this
    # account has a statement_checkpoint (i.e. has been through at least one CSV import).
    balance_cents: int
    balance_delta_cents: int | None


class CheckpointCreate(BaseModel):
    """A manually-entered statement balance anchor (ROADMAP #4). `stated_balance_cents` is signed
    in the ledger's convention — for a card, what you owe reads negative, same as its derived
    balance — so the reconciliation delta lines up with `AccountOut.balance_cents`."""

    statement_date: date_
    stated_balance_cents: int

    @field_validator("statement_date")
    @classmethod
    def not_in_future(cls, v: date_) -> date_:
        if v > date_.today():
            raise ValueError("statement_date cannot be in the future")
        return v


class CheckpointOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    statement_date: date_
    stated_balance_cents: int
    # None for a manually-entered checkpoint; set when it came from a CSV import batch.
    import_batch_id: uuid.UUID | None
