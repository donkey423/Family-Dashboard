from ...storage.ports import StoragePort
from .ports import DocumentSourceReference, DocumentSourceUnavailable


class LocalFileDocumentSource:
    source_type = "local_file"

    def __init__(self, storage: StoragePort):
        self.storage = storage

    def read(self, reference: DocumentSourceReference) -> bytes:
        if not reference.storage_key:
            raise DocumentSourceUnavailable("文件沒有本機儲存位置")
        return self.storage.read(reference.storage_key)
