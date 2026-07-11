import datetime
import uuid

from pydantic import BaseModel


class BudgetCreate(BaseModel):
    category_id: uuid.UUID
    month: datetime.date  # first-of-month marker, e.g. 2026-07-01
    amount: int  # signed integer cents — a budget is a positive cap, stored as given


class BudgetUpdate(BaseModel):
    amount: int  # the new monthly cap, positive cents — how a coach cut draft is accepted


class BudgetOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    month: datetime.date
    amount: int
    # Computed at read time (mirrors AccountOut's balance fields, Phase 3) — the actual
    # spend/refund total for this category+month, never stored.
    actual_cents: int


class BudgetProposalOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    suggested_amount_cents: int  # trailing-3-month median spend for this category
