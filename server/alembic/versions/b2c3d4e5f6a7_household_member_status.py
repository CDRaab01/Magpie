"""household_members.status (pending invites)

Adds a ``status`` ("active" | "pending") to household_members so an invite doesn't share the ledger
until the invitee accepts. Existing rows default to "active" (already-sharing members stay sharing).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "household_members",
        sa.Column("status", sa.String(length=10), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_column("household_members", "status")
