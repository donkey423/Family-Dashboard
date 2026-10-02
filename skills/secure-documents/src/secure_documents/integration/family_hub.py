from __future__ import annotations

import sqlite3
from pathlib import Path

PERSONAL_UNLOCK_ID = "personal-unlock"


def read_family_hub_credential_refs(db_path: Path) -> tuple[str | None, str | None]:
    """Read credential *references* only, never the underlying secret values."""

    uri = f"file:{db_path.expanduser().resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            "SELECT national_id_credential_ref, birthday_credential_ref "
            "FROM secret_profiles WHERE id = ?",
            (PERSONAL_UNLOCK_ID,),
        ).fetchone()
    if row is None:
        return None, None
    return row[0] or None, row[1] or None
