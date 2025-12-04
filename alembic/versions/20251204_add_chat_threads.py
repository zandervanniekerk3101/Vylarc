"""add chat threads and link to chat history

Revision ID: 20251204_add_chat_threads
Revises: f6d5e4c3b2a1
Create Date: 2025-12-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251204_add_chat_threads'
down_revision = 'f6d5e4c3b2a1'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'chat_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.add_column('chat_history', sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_chat_history_thread', 'chat_history', 'chat_threads', ['thread_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_chat_history_thread_id', 'chat_history', ['thread_id'])


def downgrade() -> None:
    op.drop_index('ix_chat_history_thread_id', table_name='chat_history')
    op.drop_constraint('fk_chat_history_thread', 'chat_history', type_='foreignkey')
    op.drop_column('chat_history', 'thread_id')
    op.drop_table('chat_threads')
