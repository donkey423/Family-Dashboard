from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader, PdfWriter
import pytest
from sqlalchemy import select

from family_finance_hub.application.pdf_processing import (
    PdfPreviewCommand,
    PdfPreviewUseCase,
    match_profiles_by_sender,
    sender_pattern_matches,
)
from family_finance_hub.database import Base, make_engine, make_session_factory
from family_finance_hub.documents.processors.pdf import PdfDocumentProcessor
from family_finance_hub.documents.processors.ports import DocumentProcessingError
from family_finance_hub.documents.sources.ports import SourceMessageContext
from family_finance_hub.documents.sources.registry import DocumentSourceRegistry
from family_finance_hub.models import (
    Document,
    DocumentSecurityProfile,
    DocumentSourceRecord,
    PasswordRuleRecord,
    SecretProfile,
)
from family_finance_hub.security.password_rules import PasswordInstructionContext, PasswordInstructionExtractor
from family_finance_hub.security.password_rules.schema import PasswordRule
from family_finance_hub.security.password_rules.service import PasswordRuleService


@dataclass(frozen=True)
class Profile:
    sender_pattern: str | None


def test_sender_pattern_ignores_display_name_and_matches_exact_email():
    assert sender_pattern_matches(
        "statements@example.test",
        "Bank Billing <Statements@Example.Test>",
    )
    assert not sender_pattern_matches("statements@example.test", "other@example.test")


def test_sender_pattern_domain_match_is_exact_and_does_not_match_subdomain():
    assert sender_pattern_matches("@example.test", "billing@example.test")
    assert not sender_pattern_matches("@example.test", "billing@sub.example.test")
    assert not sender_pattern_matches("example.test", "billing@example.test")


def test_profile_match_requires_exactly_one_candidate():
    profiles = [Profile("@example.test"), Profile("billing@example.test")]

    ambiguous = match_profiles_by_sender(profiles, "Billing <billing@example.test>")
    assert len(ambiguous.candidates) == 2
    assert ambiguous.profile is None

    unique = match_profiles_by_sender([Profile("@example.test"), Profile("other.test")], "billing@example.test")
    assert len(unique.candidates) == 1
    assert unique.profile is not None

    none = match_profiles_by_sender(profiles, "billing@other.test")
    assert none.candidates == ()
    assert none.profile is None


@pytest.mark.parametrize("sender", [
    "not-an-email",
    "statements@example.test, alerts@example.test",
    "statements@example.test, malformed",
    "Billing <statements@example.test",
    "statements@example.test\nBcc: alerts@example.test",
])
def test_sender_profile_matching_rejects_malformed_or_multiple_addresses(sender):
    assert match_profiles_by_sender([Profile("@example.test")], sender).profile is None
    assert not sender_pattern_matches("@example.test", sender)


class MemoryDocumentSource:
    source_type = "memory_pdf"

    def __init__(self, content):
        self.content = content

    def read(self, reference):
        return self.content


class MemoryMessageContextSource:
    def read_message_context(self, reference):
        return SourceMessageContext(
            subject="Synthetic statement password rule",
            sender="billing@bank.example",
            body="Password rule: national ID suffix plus birthday YYYYMMDD.",
        )


class MemorySecretStore:
    def __init__(self, values):
        self.values = values
        self.get_calls = []

    def get(self, reference):
        self.get_calls.append(reference)
        return self.values.get(reference)


def _encrypted_pdf(password):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _resolved_password_rule():
    return PasswordRule.model_validate({
        "version": 1,
        "status": "resolved",
        "candidates": [{
            "parts": [
                {"source": "national_id", "transform": "suffix", "start": None, "length": 4, "date_format": None, "case": "upper"},
                {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYYYMMDD", "case": "preserve"},
            ],
            "separator": "",
        }],
    })


@pytest.mark.parametrize(("password", "opens"), [
    ("678919840302", True),
    ("432119850403", False),
])
def test_pdf_preview_use_case_reuses_verified_rule_and_reads_only_matched_profile_secret(password, opens):
    original_pdf = _encrypted_pdf(password)
    source = MemoryDocumentSource(original_pdf)
    source_registry = DocumentSourceRegistry((source,))
    message_source = MemoryMessageContextSource()
    secret_store = MemorySecretStore({
        "secret:matched:id": "A123456789",
        "secret:matched:birthday": "1984-03-02",
        "secret:other:id": "B987654321",
        "secret:other:birthday": "1985-04-03",
    })
    extractor = PasswordInstructionExtractor()
    password_rules = PasswordRuleService()
    command = PdfPreviewCommand()
    message_context = SourceMessageContext(
        "Synthetic statement password rule",
        "billing@bank.example",
        "Password rule: national ID suffix plus birthday YYYYMMDD.",
    )
    instruction = extractor.extract(
        PasswordInstructionContext(
            message_context.subject,
            message_context.body,
            message_context.sender,
            "synthetic-statement.pdf",
        ),
        ("A123456789", "19840302"),
    )
    context = {"institution": "Synthetic Bank", "document_type": "PDF statement"}
    fingerprint = password_rules.fingerprint(instruction, context)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    use_case = PdfPreviewUseCase(
        source_registry,
        message_source,
        PdfDocumentProcessor(),
        extractor,
        password_rules,
        lambda: secret_store,
        lambda session: pytest.fail("verified rule should avoid AI"),
    )

    try:
        with factory() as session:
            document = Document(
                id="synthetic-document",
                sha256=sha256(original_pdf).hexdigest(),
                filename="synthetic-statement.pdf",
                content_type="application/pdf",
                size_bytes=len(original_pdf),
            )
            document.sources.extend([
                DocumentSourceRecord(
                    id="memory-source",
                    source_type="memory_pdf",
                    source_key="memory:statement",
                    availability_status="available",
                ),
                DocumentSourceRecord(
                    id="gmail-source",
                    source_type="gmail_attachment",
                    source_key="gmail:statement",
                    source_reference={"message_id": "synthetic-message"},
                    availability_status="available",
                ),
            ])
            session.add_all([
                document,
                SecretProfile(
                    id="matched-secret",
                    display_name="Synthetic household member",
                    national_id_credential_ref="secret:matched:id",
                    birthday_credential_ref="secret:matched:birthday",
                ),
                SecretProfile(
                    id="other-secret",
                    display_name="Other synthetic member",
                    national_id_credential_ref="secret:other:id",
                    birthday_credential_ref="secret:other:birthday",
                ),
                DocumentSecurityProfile(
                    id="matched-profile",
                    display_name="Synthetic statement profile",
                    institution="Synthetic Bank",
                    sender_pattern="@bank.example",
                    secret_profile_id="matched-secret",
                ),
                DocumentSecurityProfile(
                    id="other-profile",
                    display_name="Other bank profile",
                    institution="Other Bank",
                    sender_pattern="@other.example",
                    secret_profile_id="other-secret",
                ),
            ])
            session.flush()
            password_rules.save_verified(
                session,
                "matched-profile",
                fingerprint,
                _resolved_password_rule(),
            )
            session.commit()

            if opens:
                result = use_case.execute(session, "synthetic-document", command)
                assert result.filename == "synthetic-statement.pdf"
                assert result.processed.was_encrypted
                assert not PdfReader(BytesIO(result.processed.preview_bytes)).is_encrypted
            else:
                with pytest.raises(DocumentProcessingError) as error:
                    use_case.execute(session, "synthetic-document", command)
                assert error.value.code == "pdf_wrong_password"
            assert source.content == original_pdf
            assert set(secret_store.get_calls) == {
                "secret:matched:id",
                "secret:matched:birthday",
            }
            assert session.scalar(select(PasswordRuleRecord)) is not None
    finally:
        engine.dispose()
