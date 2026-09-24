"""Store Gmail OAuth credential references only."""
from alembic import op
import sqlalchemy as sa

revision = "0006_gmail_connection"
down_revision = "0005_password_rules_ai_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_config_credential_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("token_credential_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gmail_connections")
