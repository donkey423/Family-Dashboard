from typing import Protocol, TypeVar

ProcessedDocument_co = TypeVar("ProcessedDocument_co", covariant=True)


class DocumentProcessor(Protocol[ProcessedDocument_co]):
    def process(self, content: bytes) -> ProcessedDocument_co: ...
