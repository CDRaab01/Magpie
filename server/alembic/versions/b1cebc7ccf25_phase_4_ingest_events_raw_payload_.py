"""phase 4: ingest_events gains raw_payload, account_id, user_id

Revision ID: b1cebc7ccf25
Revises: dc0b90fcfb82
Create Date: 2026-07-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1cebc7ccf25'
down_revision: Union[str, None] = 'dc0b90fcfb82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # raw_payload: the full email body, kept even for unparsed/duplicate outcomes so a fixed
    # parser can replay history (CLAUDE.md §9/§10) — payload_hash alone can dedupe but can't
    # be reparsed.
    op.add_column('ingest_events', sa.Column('raw_payload', sa.Text(), nullable=False, server_default=''))
    op.alter_column('ingest_events', 'raw_payload', server_default=None)
    # account_id: nullable because a parsed event may fail to resolve an account (last4 with
    # no match) — that's still a real ingest_event (outcome tracks the failure), just an
    # orphaned one.
    op.add_column('ingest_events', sa.Column('account_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_ingest_events_account_id', 'ingest_events', 'accounts', ['account_id'], ['id'],
        ondelete='SET NULL',
    )
    # user_id: every ingest event is scoped to the household member whose mailbox produced it
    # (same CurrentUser scoping convention as every other table).
    op.add_column('ingest_events', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.execute("UPDATE ingest_events SET user_id = (SELECT id FROM users LIMIT 1)")
    op.alter_column('ingest_events', 'user_id', nullable=False)
    op.create_foreign_key(
        'fk_ingest_events_user_id', 'ingest_events', 'users', ['user_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index(op.f('ix_ingest_events_user_id'), 'ingest_events', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ingest_events_user_id'), table_name='ingest_events')
    op.drop_constraint('fk_ingest_events_user_id', 'ingest_events', type_='foreignkey')
    op.drop_column('ingest_events', 'user_id')
    op.drop_constraint('fk_ingest_events_account_id', 'ingest_events', type_='foreignkey')
    op.drop_column('ingest_events', 'account_id')
    op.drop_column('ingest_events', 'raw_payload')
