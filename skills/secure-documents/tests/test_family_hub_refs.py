import sqlite3

from secure_documents.integration.family_hub import read_family_hub_credential_refs


def test_reads_only_personal_unlock_references(tmp_path):
    db = tmp_path / "hub.db"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE secret_profiles (id TEXT PRIMARY KEY, national_id_credential_ref TEXT, birthday_credential_ref TEXT)"
        )
        connection.execute(
            "INSERT INTO secret_profiles VALUES (?, ?, ?)",
            ("personal-unlock", "personal-unlock:test:id", "personal-unlock:test:birthday"),
        )
    assert read_family_hub_credential_refs(db) == (
        "personal-unlock:test:id",
        "personal-unlock:test:birthday",
    )
