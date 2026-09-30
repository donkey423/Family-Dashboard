"""Isolated real-statement acceptance server with read-only credential access."""
import argparse
import os
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import uvicorn

from family_finance_hub.config import Settings
from family_finance_hub.security.secrets import KeyringSecretStore, SecretStoreUnavailable


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_ROOT = ROOT / "data" / "gmail-acceptance"


def acceptance_directory(value: str) -> Path:
    directory = Path(value).resolve()
    if not directory.is_relative_to(ACCEPTANCE_ROOT.resolve()) or not directory.name.startswith("retest-"):
        raise ValueError("Use a retest-* directory inside data/gmail-acceptance only")
    return directory


class ReadOnlyCredentials:
    def __init__(self):
        self.store = KeyringSecretStore()

    def get(self, reference):
        return self.store.get(reference)

    def set(self, reference, value):
        raise SecretStoreUnavailable("Acceptance tests cannot change saved credentials")

    def delete(self, reference):
        raise SecretStoreUnavailable("Acceptance tests cannot delete saved credentials")


class NoExternalAI:
    calls = 0

    def interpret(self, instruction, context):
        self.calls += 1
        raise RuntimeError("External AI is disabled in this acceptance server")


def create_acceptance_app(directory: Path):
    directory = acceptance_directory(str(directory))
    directory.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{(directory / 'acceptance.db').as_posix()}"
    # Alembic's environment overrides its Config URL, so pin both to the guarded DB.
    os.environ["FAMILY_FINANCE_HUB_DATABASE_URL"] = database_url
    os.environ["FAMILY_FINANCE_HUB_STORAGE_ROOT"] = str(directory / "documents")
    os.environ["FAMILY_FINANCE_HUB_EXCEL_PATH"] = str(directory / "exports" / "家庭收支記錄.xlsx")
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    from family_finance_hub.main import create_app
    from family_finance_hub.models import DocumentSecurityProfile, SecretProfile

    interpreter = NoExternalAI()
    app = create_app(Settings.from_environment(), secret_store=ReadOnlyCredentials(), password_interpreter=interpreter)

    @app.get("/api/acceptance/status")
    def acceptance_status():
        return {"mode": "isolated-gmail-acceptance", "run_directory": directory.name,
                "external_ai_calls": interpreter.calls}

    # The application's static frontend mount otherwise shadows this test-only route.
    app.router.routes.insert(0, app.router.routes.pop())

    live_database = ROOT / "data" / "family-finance-hub-live.db"
    with sqlite3.connect(live_database.as_uri() + "?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        profile = source.execute("SELECT * FROM secret_profiles WHERE id = ?", ("personal-unlock",)).fetchone()
        security = source.execute("SELECT * FROM document_security_profiles WHERE id = ?", ("personal-unlock",)).fetchone()
    if profile is None or security is None:
        raise RuntimeError("The existing personal unlock profile is required")
    with app.state.session_factory() as session, session.begin():
        if session.get(SecretProfile, "personal-unlock") is None:
            copied = SecretProfile(id=profile["id"], display_name=profile["display_name"],
                national_id_credential_ref=profile["national_id_credential_ref"],
                birthday_credential_ref=profile["birthday_credential_ref"])
            session.add(copied)
            session.add(DocumentSecurityProfile(id=security["id"], display_name=security["display_name"],
                institution=security["institution"], sender_pattern=security["sender_pattern"], secret_profile=copied))
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--port", type=int, default=8031)
    args = parser.parse_args()
    if args.port < 8031:
        parser.error("Do not use a production or synthetic-preview API port")
    uvicorn.run(create_acceptance_app(acceptance_directory(args.run_directory)), host="127.0.0.1", port=args.port, access_log=False)
