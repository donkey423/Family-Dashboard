from collections.abc import Iterable

from ...models import Document
from .ports import DocumentSource, DocumentSourceReference, DocumentSourceUnavailable


class DocumentSourceRegistry:
    def __init__(self, sources: Iterable[DocumentSource]):
        self._sources = {source.source_type: source for source in sources}

    def read(self, document: Document) -> bytes:
        source = self._sources.get(document.source_type)
        if source is None:
            raise DocumentSourceUnavailable(f"尚未設定 {document.source_type} 文件來源")
        return source.read(DocumentSourceReference(
            storage_key=document.storage_key,
            metadata=document.source_reference,
        ))
