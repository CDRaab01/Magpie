"""import_batches.user_id scoping (#7)

`import_batches` was the last unscoped table — no `user_id`, no FK to anything. Adds the owner
column (nullable + additive, like the budgets scoping), backfills it from each batch's transactions
where they unambiguously resolve to a single user, and leaves attribution-less residue (batches with
no surviving transactions — ~88 of 119 rows are test residue) NULL. The app sets `user_id` on every
new batch; any future read of the table filters on it.

Revision ID: a2f9d3c1e8b7
Revises: a1d4c7e2b905
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2f9d3c1e8b7"
down_revision: Union[str, None] = "a1d4c7e2b905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("import_batches", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_import_batches_user_id"), "import_batches", ["user_id"], unique=False
    )
    op.create_foreign_key(
        "fk_import_batches_user_id_users",
        "import_batches",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Backfill from the batch's transactions -> account owner, but only where every transaction of
    # the batch resolves to one user (HAVING COUNT(DISTINCT ...) = 1). A batch whose transactions
    # were all pruned (test residue) has no rows here and stays NULL.
    op.execute(
        """
        UPDATE import_batches b
        SET user_id = sub.uid
        FROM (
            SELECT t.import_batch_id AS bid,
                   (array_agg(DISTINCT a.user_id))[1] AS uid
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.import_batch_id IS NOT NULL
            GROUP BY t.import_batch_id
            HAVING COUNT(DISTINCT a.user_id) = 1
        ) sub
        WHERE b.id = sub.bid
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_import_batches_user_id_users", "import_batches", type_="foreignkey"
    )
    op.drop_index(op.f("ix_import_batches_user_id"), table_name="import_batches")
    op.drop_column("import_batches", "user_id")
