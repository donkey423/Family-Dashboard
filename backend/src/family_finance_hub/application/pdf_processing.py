from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import Parser
from typing import Callable, Generic, Iterable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..documents.processors.ports import (
    DocumentProcessingError,
    PasswordAwarePdfProcessor,
    PdfProcessingResult,
    ProcessingContext,
    ProcessingRequest,
)
from ..documents.sources.ports import (
    DocumentSourceUnavailable,
    MessageContextSource,
    SourceMessageContext,
)
from ..documents.sources.registry import DocumentSourceRegistry
from ..models import (
    Document,
    DocumentSecurityProfile,
    DocumentSourceRecord,
    SecretProfile,
)
from ..security.password_rules import (
    ExplicitPasswordRuleParser,
    PasswordComposer,
    PasswordInstructionContext,
    PasswordInstructionExtractor,
)
from ..security.password_rules.ports import PasswordRuleInterpreter
from ..security.password_rules.service import PasswordRuleService
from ..security.secrets.ports import SecretStore
from ..security.secrets.service import PERSONAL_UNLOCK_ID


ProfileT = TypeVar("ProfileT")


@dataclass(frozen=True)
class ProfileMatchResult(Generic[ProfileT]):
    candidates: tuple[ProfileT, ...]

    @property
    def profile(self) -> ProfileT | None:
        return self.candidates[0] if len(self.candidates) == 1 else None


def match_profiles_by_sender(
    profiles: Iterable[ProfileT],
    sender: str,
) -> ProfileMatchResult[ProfileT]:
    address = _sender_address(sender)
    if not address:
        return ProfileMatchResult(())
    matches = tuple(
        profile for profile in profiles
        if sender_pattern_matches(getattr(profile, "sender_pattern", None), address)
    )
    return ProfileMatchResult(matches)


def sender_pattern_matches(pattern: str | None, sender: str) -> bool:
    normalized_pattern = (pattern or "").strip().casefold()
    if not normalized_pattern:
        return False
    address = _sender_address(sender)
    if not address:
        return False
    if normalized_pattern.startswith("@"):
        domain = normalized_pattern[1:]
        return _valid_domain(domain) and address.rsplit("@", 1)[1] == domain
    if normalized_pattern.count("@") != 1:
        return False
    local, domain = normalized_pattern.rsplit("@", 1)
    if not local or any(character.isspace() or character in "<>," for character in local):
        return False
    return _valid_domain(domain) and address == normalized_pattern


def _sender_address(sender: str) -> str:
    value = sender.strip()
    if not value or "\r" in value or "\n" in value:
        return ""
    try:
        header = Parser(policy=policy.default).parsestr(f"From: {value}\n\n")["From"]
        if header is None or header.defects or len(header.addresses) != 1:
            return ""
        address = header.addresses[0].addr_spec.strip().casefold()
    except (AttributeError, TypeError, ValueError):
        return ""
    if address.count("@") != 1:
        return ""
    local, domain = address.rsplit("@", 1)
    if not local or not _valid_domain(domain):
        return ""
    return address


def _valid_domain(domain: str) -> bool:
    labels = domain.split(".")
    return (
        len(labels) >= 2
        and all(label and label[0].isalnum() and label[-1].isalnum() for label in labels)
        and all(all(character.isalnum() or character == "-" for character in label) for label in labels)
    )


@dataclass(frozen=True)
class PdfPreviewCommand:
    document_security_profile_id: str | None = None
    subject: str = ""
    body: str = ""
    sender: str = ""
    filename: str = ""
    allow_ai_analysis: bool = False


@dataclass(frozen=True)
class PdfPreviewResult:
    filename: str
    processed: PdfProcessingResult


class PdfPreviewDocumentNotFound(Exception):
    pass


class PdfPreviewProfileNotFound(Exception):
    pass


class PdfPreviewSecretProfileNotFound(Exception):
    pass


class PdfPreviewUnsupportedDocument(Exception):
    pass


class PdfPreviewUseCase:
    def __init__(
        self,
        document_sources: DocumentSourceRegistry,
        message_context_source: MessageContextSource,
        pdf_processor: PasswordAwarePdfProcessor,
        instruction_extractor: PasswordInstructionExtractor,
        password_rules: PasswordRuleService,
        secret_store_factory: Callable[[], SecretStore],
        interpreter_factory: Callable[[Session], PasswordRuleInterpreter],
        explicit_rule_parser: ExplicitPasswordRuleParser | None = None,
    ):
        self.document_sources = document_sources
        self.message_context_source = message_context_source
        self.pdf_processor = pdf_processor
        self.instruction_extractor = instruction_extractor
        self.password_rules = password_rules
        self.secret_store_factory = secret_store_factory
        self.interpreter_factory = interpreter_factory
        self.explicit_rule_parser = explicit_rule_parser or ExplicitPasswordRuleParser()

    def execute(
        self,
        session: Session,
        document_id: str,
        command: PdfPreviewCommand,
    ) -> PdfPreviewResult:
        with session.begin():
            document = session.get(Document, document_id)
            if document is None:
                raise PdfPreviewDocumentNotFound
            if document.content_type != "application/pdf" and not document.filename.lower().endswith(".pdf"):
                raise PdfPreviewUnsupportedDocument
            try:
                content = self.document_sources.read(document)
            except DocumentSourceUnavailable:
                content = None
            gmail_references = session.scalars(select(DocumentSourceRecord).where(
                DocumentSourceRecord.document_id == document_id,
                DocumentSourceRecord.source_type == "gmail_attachment",
            )).all()
            profile = (
                session.get(DocumentSecurityProfile, command.document_security_profile_id)
                if command.document_security_profile_id
                else session.get(DocumentSecurityProfile, PERSONAL_UNLOCK_ID)
            )
            if command.document_security_profile_id and profile is None:
                raise PdfPreviewProfileNotFound
            secret_profile = session.get(SecretProfile, profile.secret_profile_id) if profile else None
            if profile and secret_profile is None:
                raise PdfPreviewSecretProfileNotFound

        if content is None:
            raise DocumentSourceUnavailable("document source unavailable")

        request = ProcessingRequest(
            content=content,
            context=ProcessingContext(
                filename=document.filename,
                content_type=document.content_type,
                document_security_profile_id=profile.id if profile else None,
            ),
        )
        rule = None
        fingerprint = ""
        processed = None
        candidate_rule_indexes: tuple[int, ...] = ()
        try:
            processed = self.pdf_processor.process(request)
        except DocumentProcessingError as initial_error:
            if initial_error.code != "pdf_password_required":
                raise
            message_context = self._message_context(gmail_references)
            if profile is None:
                profiles = session.scalars(select(DocumentSecurityProfile)).all()
                matched = match_profiles_by_sender(
                    profiles,
                    message_context.sender if message_context else command.sender,
                )
                profile = matched.profile
                if profile is not None:
                    secret_profile = session.get(SecretProfile, profile.secret_profile_id)
                else:
                    raise DocumentProcessingError(
                        "pdf_password_required",
                        "寄件者無法唯一匹配文件解鎖設定",
                    ) from None
            if secret_profile is None:
                raise DocumentProcessingError("pdf_password_required", "文件解鎖設定缺少安全資料") from None

            request = ProcessingRequest(
                content=content,
                context=ProcessingContext(
                    filename=document.filename,
                    content_type=document.content_type,
                    document_security_profile_id=profile.id,
                ),
            )
            secret_store = self.secret_store_factory()
            national_id = secret_store.get(secret_profile.national_id_credential_ref)
            birthday = secret_store.get(secret_profile.birthday_credential_ref)
            if not national_id and not birthday:
                raise DocumentProcessingError("pdf_password_required", "尚未保存可用的解鎖資料") from None
            instruction = self.instruction_extractor.extract(
                PasswordInstructionContext(
                    message_context.subject if message_context else command.subject,
                    message_context.body if message_context else command.body,
                    message_context.sender if message_context else command.sender,
                    command.filename or document.filename,
                ),
                (value for value in (national_id, birthday) if value),
            )
            if not instruction:
                raise initial_error
            context = (
                {"document_type": "PDF"}
                if profile.id == PERSONAL_UNLOCK_ID
                else {"institution": profile.institution, "document_type": "PDF statement"}
            )
            fingerprint = self.password_rules.fingerprint(instruction, context)
            explicit_rule = self.explicit_rule_parser.parse(instruction)
            cached_rule = self.password_rules.get_verified(session, profile.id, fingerprint)
            rule = explicit_rule or cached_rule
            session.commit()
            if rule:
                candidates, candidate_rule_indexes = PasswordComposer(secret_store).compose_with_rule_indexes(
                    rule,
                    secret_profile.national_id_credential_ref,
                    secret_profile.birthday_credential_ref,
                )
            else:
                candidates = ()
            if candidates:
                try:
                    processed = self.pdf_processor.process(request, password_candidates=candidates)
                except DocumentProcessingError as cached_error:
                    if (
                        cached_error.code != "pdf_wrong_password"
                        or explicit_rule is not None
                        or not command.allow_ai_analysis
                    ):
                        raise
                    rule = None
            else:
                rule = None

            if processed is None:
                if explicit_rule is not None:
                    raise DocumentProcessingError(
                        "pdf_password_required",
                        "郵件已說明密碼格式，但尚未保存所需的身分資料",
                    ) from None
                if not command.allow_ai_analysis:
                    raise DocumentProcessingError(
                        "pdf_password_required",
                        "郵件中沒有可由本機確認的密碼格式，且尚無已驗證的密碼規則",
                    ) from None
                interpreter = self.interpreter_factory(session)
                session.commit()
                rule = interpreter.interpret(instruction, context)
                candidates, candidate_rule_indexes = PasswordComposer(secret_store).compose_with_rule_indexes(
                    rule,
                    secret_profile.national_id_credential_ref,
                    secret_profile.birthday_credential_ref,
                )
                if not candidates:
                    raise DocumentProcessingError("pdf_password_required", "密碼規則不明確或無法使用") from None
                processed = self.pdf_processor.process(request, password_candidates=candidates)

        if processed is None:
            raise DocumentProcessingError("pdf_malformed", "PDF 無法處理") from None
        if processed.was_encrypted and rule is not None and fingerprint:
            if rule.status == "ambiguous" and processed.successful_candidate_index is not None:
                try:
                    rule_index = candidate_rule_indexes[processed.successful_candidate_index]
                except IndexError:
                    raise DocumentProcessingError("pdf_malformed", "PDF 密碼規則結果無法對應") from None
                selected = rule.candidates[rule_index]
                rule = rule.model_copy(update={"status": "resolved", "candidates": [selected]})
            if rule.status == "resolved" and profile:
                self.password_rules.save_verified(session, profile.id, fingerprint, rule)
                session.commit()
        return PdfPreviewResult(document.filename, processed)

    def _message_context(
        self,
        source_records: Iterable[DocumentSourceRecord],
    ) -> SourceMessageContext | None:
        for source in source_records:
            try:
                return self.message_context_source.read_message_context(source.source_reference or {})
            except DocumentSourceUnavailable:
                continue
        return None
