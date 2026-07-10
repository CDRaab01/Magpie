"""One bill per matched transaction (F13)

Two bills of the same amount on the same payment rail could both point at the single payment
that settled only one of them — the second bill then looked paid and its missing-bill alert
never fired. `bill_service` now excludes already-claimed transactions when matching; this
partial unique index is the durable backstop, so the invariant survives any future caller.

Partial (`WHERE matched_transaction_id IS NOT NULL`) because unmatched bills are the normal
state and NULLs must stay free to repeat.

Revision ID: a1d4c7e2b905
Revises: f3b8c2e9a1d7
Create Date: 2026-07-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1d4c7e2b905"
down_revision: Union[str, None] = "f3b8c2e9a1d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_bill_statements_matched_transaction_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "bill_statements",
        ["matched_transaction_id"],
        unique=True,
        postgresql_where=sa.text("matched_transaction_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="bill_statements")
