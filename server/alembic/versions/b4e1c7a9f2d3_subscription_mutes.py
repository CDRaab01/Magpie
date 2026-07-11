"""subscription_mutes (#12)

A per-merchant "not a subscription" mute so the Subscriptions screen and the two subscription
sweeps skip the honest-but-noisy recurrences (a weekly gas stop, a Cash-App-to-a-person, the
mortgage that counts twice across a servicer transfer). Additive; nothing references it until the
app writes mutes.

Revision ID: b4e1c7a9f2d3
Revises: a2f9d3c1e8b7
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e1c7a9f2d3"
down_revision: Union[str, None] = "a2f9d3c1e8b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_mutes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "merchant", name="uq_subscription_mute_user_merchant"),
    )
    op.create_index(
        op.f("ix_subscription_mutes_user_id"), "subscription_mutes", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscription_mutes_user_id"), table_name="subscription_mutes")
    op.drop_table("subscription_mutes")
