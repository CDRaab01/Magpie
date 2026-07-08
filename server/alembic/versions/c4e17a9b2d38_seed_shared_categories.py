"""seed shared categories (V1.md Tier 1 #8)

Insert the shared category vocabulary (user_id NULL — available to every user). Without a
seeded vocabulary the AI categorization stage has nothing to suggest and every review-queue
confirm files uncategorized spend (CLAUDE.md §6 / V1.md Tier 1 #8). The channel-semantic
categories `Cash` and `Income` are part of the accounting model (CLAUDE.md §2/§7).

The name list is a frozen snapshot here on purpose — a migration must not drift with the app;
later additions are their own migration, and users add their own via the category CRUD.

Revision ID: c4e17a9b2d38
Revises: 11be6cf6f798
Create Date: 2026-07-08 00:00:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e17a9b2d38"
down_revision: Union[str, None] = "11be6cf6f798"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_CATEGORY_NAMES = (
    "Groceries",
    "Dining",
    "Transport",
    "Utilities",
    "Housing",
    "Subscriptions",
    "Entertainment",
    "Health",
    "Shopping",
    "Travel",
    "Cash",
    "Income",
    "Other",
)

_categories = sa.table(
    "categories",
    sa.column("id", sa.Uuid()),
    sa.column("user_id", sa.Uuid()),
    sa.column("name", sa.String()),
)


def upgrade() -> None:
    op.bulk_insert(
        _categories,
        [{"id": uuid.uuid4(), "user_id": None, "name": name} for name in SEED_CATEGORY_NAMES],
    )


def downgrade() -> None:
    op.execute(
        _categories.delete().where(
            sa.and_(
                _categories.c.user_id.is_(None),
                _categories.c.name.in_(SEED_CATEGORY_NAMES),
            )
        )
    )
