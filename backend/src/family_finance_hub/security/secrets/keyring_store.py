import os

import keyring
from keyring.backends.Windows import WinVaultKeyring

from .ports import SecretStore

SERVICE_NAME = "family-finance-hub"


class SecretStoreUnavailable(RuntimeError):
    pass


class KeyringSecretStore(SecretStore):
    def __init__(self):
        backend = keyring.get_keyring()
        if os.name != "nt" or not isinstance(backend, WinVaultKeyring):
            raise SecretStoreUnavailable("Windows Credential Manager is not available")
        self._keyring = keyring

    def set(self, reference: str, value: str) -> None:
        if not reference or not value:
            raise ValueError("Secret reference and value must not be empty")
        try:
            self._keyring.set_password(SERVICE_NAME, reference, value)
        except Exception as error:
            raise SecretStoreUnavailable("Could not save secret in Windows Credential Manager") from error

    def get(self, reference: str) -> str | None:
        try:
            return self._keyring.get_password(SERVICE_NAME, reference)
        except Exception as error:
            raise SecretStoreUnavailable("Could not read secret from Windows Credential Manager") from error

    def delete(self, reference: str) -> None:
        try:
            self._keyring.delete_password(SERVICE_NAME, reference)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as error:
            raise SecretStoreUnavailable("Could not delete secret from Windows Credential Manager") from error
