from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MemorySecretStore:
    values: dict[str, str]

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)


class WindowsCredentialStore:
    """Read-only adapter over Windows Credential Manager through keyring.

    Import is lazy so unencrypted extraction works without the optional Windows
    dependency on other platforms.
    """

    def __init__(self, service_name: str = "family-finance-hub"):
        if os.name != "nt":
            raise RuntimeError("Windows Credential Manager is available only on Windows")
        try:
            import keyring
            from keyring.backends.Windows import WinVaultKeyring
        except ImportError as error:
            raise RuntimeError("install the [windows] extra to use Windows Credential Manager") from error
        backend = keyring.get_keyring()
        if not isinstance(backend, WinVaultKeyring):
            raise RuntimeError("Windows Credential Manager backend is not active")
        self._keyring = keyring
        self._service_name = service_name

    def get(self, reference: str) -> str | None:
        return self._keyring.get_password(self._service_name, reference)
