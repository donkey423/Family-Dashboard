from collections.abc import Iterable

from ...models import Document, utc_now
from .ports import DocumentSource, DocumentSourceReference, DocumentSourceUnavailable


class DocumentSourceRegistry:
    def __init__(self, sources: Iterable[DocumentSource]):
        self._sources = {source.source_type: source for source in sources}

    def read(self, document: Document) -> bytes:
        availability_priority = {"available": 0, "unknown": 1, "unavailable": 2}
        sources = sorted(
            document.sources,
            key=lambda record: (
                availability_priority.get(record.availability_status, 1),
                record.source_type,
                record.source_key,
            ),
        )
        configured = False

        for record in sources:
            source = self._sources.get(record.source_type)
            if source is None:
                continue
            configured = True
            try:
                content = source.read(DocumentSourceReference(
                    storage_key=record.storage_key,
                    metadata=record.source_reference,
                ))
            except (DocumentSourceUnavailable, OSError):
                record.availability_status = "unavailable"
                continue

            record.availability_status = "available"
            record.last_verified_at = utc_now()
            return content

        if configured:
            raise DocumentSourceUnavailable("目前無法從已設定的文件來源取得內容")
        raise DocumentSourceUnavailable("尚未設定可讀取此文件的來源")
