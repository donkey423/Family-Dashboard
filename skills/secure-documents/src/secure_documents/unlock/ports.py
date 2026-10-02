from typing import Protocol


class SecretStore(Protocol):
    def get(self, reference: str) -> str | None: ...
