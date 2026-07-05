"""phase 5: rules gains user_id, transactions gain matched_rule_id + rule_note

Revision ID: b72a5f74739e
Revises: b1cebc7ccf25
Create Date: 2026-07-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b72a5f74739e'
down_revision: Union[str, None] = 'b1cebc7ccf25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_id: same CurrentUser-scoping convention as every other table — account_id alone
    # is nullable and insufficient to filter by owner directly (the same gap ingest_events
    # had before Phase 4).
    op.add_column('rules', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.execute("UPDATE rules SET user_id = (SELECT id FROM users LIMIT 1)")
    op.alter_column('rules', 'user_id', nullable=False)
    op.create_foreign_key(
        'fk_rules_user_id', 'rules', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index(op.f('ix_rules_user_id'), 'rules', ['user_id'], unique=False)

    # matched_rule_id + rule_note: the review queue's "why" (CLAUDE.md §5 — "matched rule:
    # XCEL monthly ±20%"), captured as a fact at evaluation time rather than re-derived later
    # from whatever the rule looks like now.
    op.add_column('transactions', sa.Column('matched_rule_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_matched_rule_id', 'transactions', 'rules', ['matched_rule_id'], ['id'],
        ondelete='SET NULL',
    )
    op.add_column('transactions', sa.Column('rule_note', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'rule_note')
    op.drop_constraint('fk_transactions_matched_rule_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'matched_rule_id')
    op.drop_index(op.f('ix_rules_user_id'), table_name='rules')
    op.drop_constraint('fk_rules_user_id', 'rules', type_='foreignkey')
    op.drop_column('rules', 'user_id')
