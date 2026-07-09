"""transaction splits (V1.md Tier 3 #26)

Adds `is_split` (marks a split parent — the real ledger row, excluded from category rollups) and
`split_parent_id` (marks a child allocation — excluded from balance/list/month totals). Additive;
existing rows get `is_split=False`, `split_parent_id=NULL` (i.e. ordinary, unsplit).

Revision ID: f3b8c2e9a1d7
Revises: e7c1a9d4f0b2
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b8c2e9a1d7"
down_revision: Union[str, None] = "e7c1a9d4f0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("is_split", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("transactions", sa.Column("split_parent_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_transactions_split_parent_id"),
        "transactions",
        ["split_parent_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_transactions_split_parent_id",
        "transactions",
        "transactions",
        ["split_parent_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_split_parent_id", "transactions", type_="foreignkey")
    op.drop_index(op.f("ix_transactions_split_parent_id"), table_name="transactions")
    op.drop_column("transactions", "split_parent_id")
    op.drop_column("transactions", "is_split")
