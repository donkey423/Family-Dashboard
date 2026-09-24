from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DocumentSourceReference:
    storage_key: str | None
    metadata: Mapping[str, str] | None


class DocumentSourceUnavailable(Exception):
    pass


class DocumentSource(Protocol):
    source_type: str

    def read(self, reference: DocumentSourceReference) -> bytes: ...
