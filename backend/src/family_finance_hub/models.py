from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sources: Mapped[list["DocumentSourceRecord"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentSourceRecord(Base):
    __tablename__ = "document_sources"
    __table_args__ = (
        UniqueConstraint("source_type", "source_key", name="uq_document_source_identity"),
        CheckConstraint(
            "availability_status IN ('available', 'unavailable', 'unknown')",
            name="ck_document_sources_availability_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_key: Mapped[str] = mapped_column(String(512))
    source_reference: Mapped[dict[str, str] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    availability_status: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="sources")


class SecretProfile(Base):
    __tablename__ = "secret_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    national_id_credential_ref: Mapped[str] = mapped_column(String(64), unique=True)
    birthday_credential_ref: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class DocumentSecurityProfile(Base):
    __tablename__ = "document_security_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    institution: Mapped[str] = mapped_column(String(100))
    sender_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_profile_id: Mapped[str] = mapped_column(ForeignKey("secret_profiles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PasswordRuleRecord(Base):
    __tablename__ = "password_rules"
    __table_args__ = (
        UniqueConstraint(
            "document_security_profile_id",
            "rule_version",
            "instruction_fingerprint",
            name="uq_password_rule_profile_version_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_security_profile_id: Mapped[str] = mapped_column(
        ForeignKey("document_security_profiles.id", ondelete="CASCADE"), index=True
    )
    rule_version: Mapped[int] = mapped_column(Integer)
    instruction_fingerprint: Mapped[str] = mapped_column(String(64))
    rule_json: Mapped[dict[str, object]] = mapped_column(JSON)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AIProviderProfile(Base):
    __tablename__ = "ai_provider_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    api_key_credential_ref: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class GmailConnection(Base):
    __tablename__ = "gmail_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_config_credential_ref: Mapped[str] = mapped_column(String(64), unique=True)
    token_credential_ref: Mapped[str] = mapped_column(String(64), unique=True)
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    next_scheduled_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class GmailSyncState(Base):
    __tablename__ = "gmail_sync_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_sync_in_progress: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    full_sync_query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_sync_page_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_sync_baseline_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="never", server_default="never")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32))
    target_module: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"
    __table_args__ = (UniqueConstraint("row_hash", name="uq_finance_transaction_row_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="TWD")
    raw_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship()
