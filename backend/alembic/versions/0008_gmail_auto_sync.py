"""Add opt-in Gmail auto-sync schedule state."""
from alembic import op
import sqlalchemy as sa

revision = "0008_gmail_auto_sync"
down_revision = "0007_gmail_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gmail_connections",
        sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "gmail_connections",
        sa.Column("next_scheduled_sync_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gmail_connections", "next_scheduled_sync_at")
    op.drop_column("gmail_connections", "auto_sync_enabled")
