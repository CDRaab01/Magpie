import uuid

from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    # True for shared/seeded categories (user_id is NULL, read-only); False for the user's own.
    shared: bool
