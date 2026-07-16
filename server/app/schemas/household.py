import uuid

from pydantic import BaseModel


class HouseholdMemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    is_owner: bool
    status: str = "active"  # "active" | "pending" (invited, not yet accepted)


class HouseholdOut(BaseModel):
    members: list[HouseholdMemberOut]
    you_are_owner: bool
    shared: bool  # more than one ACTIVE member — the ledger is actually being shared


class AddMemberRequest(BaseModel):
    email: str


class InviteOut(BaseModel):
    """A household invite awaiting the caller's response (null when there is none)."""

    household_id: uuid.UUID
    owner_name: str
    owner_email: str
