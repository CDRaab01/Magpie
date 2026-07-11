"""goals (AI budget coach)

The household's savings target — one active `monthly_savings` goal per user, enforced by a
partial unique index. Additive; nothing references it until the coach endpoints write goals.
Per-category "spend less" targets are deliberately NOT a table: the budget is the category cap,
and a cut is a lowered budget the owner confirms.

Revision ID: c9d2e4f7a1b8
Revises: b4e1c7a9f2d3
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d2e4f7a1b8"
down_revision: Union[str, None] = "b4e1c7a9f2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)
    # One ACTIVE goal per (user, kind); inactive history rows are unconstrained.
    op.create_index(
        "uq_goals_user_kind_active",
        "goals",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_index("uq_goals_user_kind_active", table_name="goals")
    op.drop_index(op.f("ix_goals_user_id"), table_name="goals")
    op.drop_table("goals")
