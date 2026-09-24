"""Persist Gmail history cursor and sync status."""
from alembic import op
import sqlalchemy as sa

revision = "0007_gmail_sync_state"
down_revision = "0006_gmail_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_sync_state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("history_id", sa.String(64), nullable=True),
        sa.Column("full_sync_in_progress", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("full_sync_query", sa.String(500), nullable=True),
        sa.Column("full_sync_page_token", sa.Text(), nullable=True),
        sa.Column("full_sync_baseline_history_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="never"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_summary", sa.String(300), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gmail_sync_state")
