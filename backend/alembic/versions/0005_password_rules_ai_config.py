"""Store verified password rules and AI provider references."""
from alembic import op
import sqlalchemy as sa

revision = "0005_password_rules_ai_config"
down_revision = "0004_secret_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_security_profile_id",
            sa.String(36),
            sa.ForeignKey("document_security_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("instruction_fingerprint", sa.String(64), nullable=False),
        sa.Column("rule_json", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_security_profile_id",
            "rule_version",
            "instruction_fingerprint",
            name="uq_password_rule_profile_version_fingerprint",
        ),
    )
    op.create_index(
        "ix_password_rules_document_security_profile_id",
        "password_rules",
        ["document_security_profile_id"],
    )
    op.create_table(
        "ai_provider_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("api_key_credential_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_provider_profiles")
    op.drop_index("ix_password_rules_document_security_profile_id", table_name="password_rules")
    op.drop_table("password_rules")
