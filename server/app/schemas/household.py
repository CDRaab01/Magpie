import uuid

from pydantic import BaseModel


class HouseholdMemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    is_owner: bool


class HouseholdOut(BaseModel):
    members: list[HouseholdMemberOut]
    you_are_owner: bool
    shared: bool  # more than one member — the ledger is actually being shared


class AddMemberRequest(BaseModel):
    email: str
