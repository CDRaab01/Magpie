"""budgets.user_id scoping (F10)

Adds the owner column so a budget is visible only to its user. Before this, `list_budgets(month)`
returned every user's budgets for the month — a cross-user leak the Budgets screen would surface.
Nullable + additive so it's safe against any pre-scoping orphan rows (which then match no user and
stay invisible); the app always sets it and the ownership filter is the read guard.

Revision ID: e7c1a9d4f0b2
Revises: d5f2a1b3c4e6
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1a9d4f0b2"
down_revision: Union[str, None] = "d5f2a1b3c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("budgets", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_budgets_user_id_users",
        "budgets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_budgets_user_id_users", "budgets", type_="foreignkey")
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_column("budgets", "user_id")
