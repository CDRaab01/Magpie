"""phase 7: transactions gain ai_suggested_category_id

Revision ID: 11be6cf6f798
Revises: b72a5f74739e
Create Date: 2026-07-05 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '11be6cf6f798'
down_revision: Union[str, None] = 'b72a5f74739e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A draft, never a confirmed fact (CLAUDE.md §6 guardrail: nothing the model produces is
    # persisted without explicit user confirmation) — kept separate from category_id so an AI
    # suggestion can never be mistaken for a human/rule decision.
    op.add_column(
        'transactions', sa.Column('ai_suggested_category_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'fk_transactions_ai_suggested_category_id', 'transactions', 'categories',
        ['ai_suggested_category_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_transactions_ai_suggested_category_id', 'transactions', type_='foreignkey'
    )
    op.drop_column('transactions', 'ai_suggested_category_id')
