from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, TypeVar

ProcessedDocument_co = TypeVar("ProcessedDocument_co", covariant=True)


@dataclass(frozen=True)
class ProcessingContext:
    filename: str
    content_type: str
    document_security_profile_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessingRequest:
    content: bytes
    context: ProcessingContext


class DocumentProcessingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DocumentProcessor(Protocol[ProcessedDocument_co]):
    def process(self, request: ProcessingRequest) -> ProcessedDocument_co: ...


@dataclass(frozen=True)
class OcrResult:
    text: str
    status: Literal["completed", "partial", "unavailable", "failed"]


class OcrProvider(Protocol):
    def extract_pdf_text(self, content: bytes, *, page_count: int) -> OcrResult: ...
