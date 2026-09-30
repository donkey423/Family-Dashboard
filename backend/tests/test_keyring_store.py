from types import SimpleNamespace

import keyring
import pytest

from family_finance_hub.security.secrets import keyring_store


class FakeWindowsKeyring:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.values = {(keyring_store.SERVICE_NAME, "existing"): "existing-value"}
        self.writes = []

    def set_password(self, service, reference, value):
        if self.fail_at == "write":
            raise OSError(1312, "No logon session")
        self.writes.append((service, reference))
        self.values[service, reference] = value

    def get_password(self, service, reference):
        if self.fail_at == "read":
            raise OSError("Read unavailable")
        if self.fail_at == "mismatch":
            return "wrong-value"
        return self.values.get((service, reference))

    def delete_password(self, service, reference):
        if self.fail_at == "delete":
            raise OSError("Delete unavailable")
        self.values.pop((service, reference))


def make_store(monkeypatch, fail_at=None):
    backend = FakeWindowsKeyring(fail_at)
    monkeypatch.setattr(keyring_store, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(keyring_store, "WinVaultKeyring", FakeWindowsKeyring)
    monkeypatch.setattr(keyring_store, "keyring", SimpleNamespace(
        get_keyring=lambda: backend,
        set_password=backend.set_password,
        get_password=backend.get_password,
        delete_password=backend.delete_password,
        errors=keyring.errors,
    ))
    return keyring_store.KeyringSecretStore(), backend


def test_access_probe_preserves_application_credentials_and_removes_probe(monkeypatch):
    store, backend = make_store(monkeypatch)
    store.verify_access()
    store.verify_access()

    assert backend.values == {(keyring_store.SERVICE_NAME, "existing"): "existing-value"}
    assert len({service for service, _ in backend.writes}) == 2
    assert all(service != keyring_store.SERVICE_NAME for service, _ in backend.writes)


@pytest.mark.parametrize("fail_at", ["write", "read", "mismatch"])
def test_access_probe_fails_closed_and_cleans_up(monkeypatch, fail_at):
    store, backend = make_store(monkeypatch, fail_at)
    with pytest.raises(keyring_store.SecretStoreUnavailable):
        store.verify_access()
    assert backend.values == {(keyring_store.SERVICE_NAME, "existing"): "existing-value"}


def test_access_probe_rejects_cleanup_failure(monkeypatch):
    store, _ = make_store(monkeypatch, "delete")
    with pytest.raises(keyring_store.SecretStoreUnavailable, match="startup probe"):
        store.verify_access()
