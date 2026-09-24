"""Add secret profiles with references only; secret values remain in the OS vault."""
from alembic import op
import sqlalchemy as sa

revision = "0004_secret_profiles"
down_revision = "0003_document_source_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secret_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("national_id_credential_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("birthday_credential_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "document_security_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("institution", sa.String(100), nullable=False),
        sa.Column("sender_pattern", sa.String(255), nullable=True),
        sa.Column("secret_profile_id", sa.String(36), sa.ForeignKey("secret_profiles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_security_profiles_secret_profile_id", "document_security_profiles", ["secret_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_document_security_profiles_secret_profile_id", table_name="document_security_profiles")
    op.drop_table("document_security_profiles")
    op.drop_table("secret_profiles")
