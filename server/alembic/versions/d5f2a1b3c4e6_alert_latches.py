"""alert latches (V1.md Tier 3 #21 / F11)

Persist alert-latch state so a deviation alert fires once per condition episode and the "already
alerted" bit survives a redeploy (the old sweep kept it in process memory, so every container
recreate re-paged the phone for a still-open condition).

Revision ID: d5f2a1b3c4e6
Revises: c4e17a9b2d38
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f2a1b3c4e6"
down_revision: Union[str, None] = "c4e17a9b2d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_latches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_key", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "alert_key", name="uq_alert_latch_user_key"),
    )
    op.create_index(op.f("ix_alert_latches_user_id"), "alert_latches", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_latches_user_id"), table_name="alert_latches")
    op.drop_table("alert_latches")
