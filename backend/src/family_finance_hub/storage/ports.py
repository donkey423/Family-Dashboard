from typing import Protocol


class StoragePort(Protocol):
    def put(self, key: str, content: bytes) -> str: ...

    def read(self, key: str) -> bytes: ...
