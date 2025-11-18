"""Initial database schema

Revision ID: f6d5e4c3b2a1
Revises: 
Create Date: 2025-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6d5e4c3b2a1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. User Credits
    op.create_table('user_credits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('balance', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # 3. User API Keys
    op.create_table('user_api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('twilio_sid', sa.Text(), nullable=True),
        sa.Column('twilio_auth', sa.Text(), nullable=True),
        sa.Column('elevenlabs_key', sa.Text(), nullable=True),
        sa.Column('elevenlabs_voice_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # 4. OAuth Tokens
    op.create_table('oauth_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_oauth_tokens_user_id'), 'oauth_tokens', ['user_id'], unique=False)

    # 5. Chat History
    op.create_table('chat_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('voice_base64', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_chat_history_user_time', 'chat_history', ['user_id', 'timestamp'], unique=False)

    # 6. Action Logs
    op.create_table('action_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action_type', sa.String(length=128), nullable=False),
        sa.Column('credits_charged', sa.Integer(), nullable=True),
        sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_action_logs_user_time', 'action_logs', ['user_id', 'timestamp'], unique=False)

    # 7. Error Logs
    op.create_table('error_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('route', sa.String(length=255), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 8. File Uploads
    op.create_table('file_uploads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=1024), nullable=True),
        sa.Column('filesize', sa.BigInteger(), nullable=True),
        sa.Column('drive_url', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_file_uploads_user_time', 'file_uploads', ['user_id', 'timestamp'], unique=False)

    # 9. Call Logs
    op.create_table('call_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('to_number', sa.String(length=64), nullable=True),
        sa.Column('from_number', sa.String(length=66), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('credits_charged', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=True),
        sa.Column('twilio_sid', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_logs_twilio_sid'), 'call_logs', ['twilio_sid'], unique=False)

    # 10. Billing Records
    op.create_table('billing_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('credits_added', sa.Integer(), nullable=False),
        sa.Column('amount_paid', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('payment_method', sa.String(length=64), nullable=True),
        sa.Column('transaction_id', sa.String(length=255), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_billing_records_transaction_id'), 'billing_records', ['transaction_id'], unique=False)

    # 11. Documents Cache
    op.create_table('documents_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('file_hash', sa.String(length=128), nullable=False),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'file_hash', name='uq_user_file_hash')
    )

    # 12. Code Runs
    op.create_table('code_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('language', sa.String(length=32), nullable=True),
        sa.Column('input_code', sa.Text(), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('errors', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('credits_charged', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # 13. Maps Queries
    op.create_table('maps_queries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('query_type', sa.String(length=64), nullable=True),
        sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('maps_queries')
    op.drop_table('code_runs')
    op.drop_table('documents_cache')
    op.drop_index(op.f('ix_billing_records_transaction_id'), table_name='billing_records')
    op.drop_table('billing_records')
    op.drop_index(op.f('ix_call_logs_twilio_sid'), table_name='call_logs')
    op.drop_table('call_logs')
    op.drop_index('idx_file_uploads_user_time', table_name='file_uploads')
    op.drop_table('file_uploads')
    op.drop_table('error_logs')
    op.drop_index('idx_action_logs_user_time', table_name='action_logs')
    op.drop_table('action_logs')
    op.drop_index('idx_chat_history_user_time', table_name='chat_history')
    op.drop_table('chat_history')
    op.drop_index(op.f('ix_oauth_tokens_user_id'), table_name='oauth_tokens')
    op.drop_table('oauth_tokens')
    op.drop_table('user_api_keys')
    op.drop_table('user_credits')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')