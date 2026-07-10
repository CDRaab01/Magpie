from pydantic import BaseModel


class RenormalizeChangeOut(BaseModel):
    old: str | None
    new: str
    count: int


class RenormalizeResultOut(BaseModel):
    dry_run: bool
    examined: int
    changed: int
    distinct_before: int
    distinct_after: int
    sample: list[RenormalizeChangeOut]
