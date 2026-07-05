from pydantic import BaseModel


class ImportSummaryOut(BaseModel):
    row_count: int
    created_count: int
    matched_count: int
    skipped_count: int
    checkpoint_created: bool
