"""merchant_tags (federated awareness Link G)

A per-merchant user tag (v1: "fitness") that unlocks a cross-app affordance — a fitness-tagged
gym membership gets its cost-per-visit shown from Spotter's training-day count. Additive; nothing
references it until the app writes tags. Mirrors subscription_mutes, plus a `tag` column and a
three-column uniqueness (a merchant can carry more than one tag).

Revision ID: d5b8e1a4c96f
Revises: c9d2e4f7a1b8
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5b8e1a4c96f"
down_revision: Union[str, None] = "c9d2e4f7a1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchant_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "merchant", "tag", name="uq_merchant_tag_user_merchant_tag"),
    )
    op.create_index(op.f("ix_merchant_tags_user_id"), "merchant_tags", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_merchant_tags_user_id"), table_name="merchant_tags")
    op.drop_table("merchant_tags")
