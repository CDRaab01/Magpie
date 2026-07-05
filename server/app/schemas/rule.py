import datetime
import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.rule import RULE_TYPES


class RuleCreate(BaseModel):
    type: str
    account_id: uuid.UUID | None = None
    matcher: str
    cadence: dict | None = None
    amount_band: dict | None = None
    category_id: uuid.UUID | None = None

    @field_validator("type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in RULE_TYPES:
            raise ValueError(f"type must be one of {RULE_TYPES}")
        return v


class RuleUpdate(BaseModel):
    matcher: str | None = None
    cadence: dict | None = None
    amount_band: dict | None = None
    category_id: uuid.UUID | None = None
    enabled: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    account_id: uuid.UUID | None
    matcher: str
    cadence: dict | None
    amount_band: dict | None
    category_id: uuid.UUID | None
    last_matched_at: datetime.datetime | None
    enabled: bool
