from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ...models import GmailConnection
from ...security.secrets.ports import SecretStore
from .client import GmailRestClient, GmailUnavailable

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_CONNECTION_ID = "gmail"


class GmailOAuthService:
    def __init__(self, secret_store: SecretStore):
        self.secret_store = secret_store

    def configure_client(self, session: Session, config: dict[str, object]) -> GmailConnection:
        installed = config.get("installed")
        if not isinstance(installed, dict) or not all(
            isinstance(installed.get(key), str) and installed[key].strip()
            for key in ("client_id", "client_secret", "auth_uri", "token_uri")
        ):
            raise ValueError("請提供 Google OAuth 桌面應用程式 JSON 設定")

        client_ref = str(uuid4())
        old_client_ref = None
        token_ref = str(uuid4())
        try:
            with session.begin():
                old = session.get(GmailConnection, GMAIL_CONNECTION_ID)
                old_client_ref = old.client_config_credential_ref if old else None
                old_token_ref = old.token_credential_ref if old else None
                self.secret_store.set(client_ref, json.dumps(config, separators=(",", ":")))
                connection = old or GmailConnection(
                    id=GMAIL_CONNECTION_ID,
                    client_config_credential_ref=client_ref,
                    token_credential_ref=token_ref,
                )
                connection.client_config_credential_ref = client_ref
                if old is None:
                    connection.token_credential_ref = token_ref
                else:
                    connection.auto_sync_enabled = False
                    connection.next_scheduled_sync_at = None
                session.add(connection)
        except Exception:
            self.secret_store.delete(client_ref)
            raise
        if old_client_ref and old_client_ref != client_ref:
            self.secret_store.delete(old_client_ref)
        if old_token_ref:
            self.secret_store.delete(old_token_ref)
        return connection

    def authorize(self, session: Session) -> None:
        connection = self._connection(session)
        config_text = self.secret_store.get(connection.client_config_credential_ref)
        if not config_text:
            raise GmailAuthorizationUnavailable("Gmail OAuth 設定不存在")
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_config(json.loads(config_text), [GMAIL_READONLY_SCOPE])
            credentials = flow.run_local_server(
                host="127.0.0.1",
                port=0,
                open_browser=True,
                access_type="offline",
                prompt="consent",
            )
            self.secret_store.set(connection.token_credential_ref, credentials.to_json())
        except GmailAuthorizationUnavailable:
            raise
        except Exception:
            raise GmailAuthorizationUnavailable("Gmail 授權未完成") from None

    def authorized_client(self, session: Session) -> GmailRestClient:
        connection = self._connection(session)
        token_text = self.secret_store.get(connection.token_credential_ref)
        if not token_text:
            raise GmailAuthorizationUnavailable("請先完成 Gmail 授權")
        try:
            from google.auth.transport.requests import AuthorizedSession, Request
            from google.oauth2.credentials import Credentials

            credentials = Credentials.from_authorized_user_info(json.loads(token_text), [GMAIL_READONLY_SCOPE])
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self.secret_store.set(connection.token_credential_ref, credentials.to_json())
            if not credentials.valid:
                raise GmailAuthorizationUnavailable("Gmail 授權已失效，請重新連線")
            return GmailRestClient(AuthorizedSession(credentials))
        except GmailAuthorizationUnavailable:
            raise
        except Exception:
            raise GmailAuthorizationUnavailable("Gmail 授權目前無法使用，請重新連線") from None

    @staticmethod
    def _connection(session: Session) -> GmailConnection:
        connection = session.get(GmailConnection, GMAIL_CONNECTION_ID)
        if connection is None:
            raise GmailAuthorizationUnavailable("請先設定 Gmail OAuth 桌面應用程式")
        return connection


class GmailAuthorizationUnavailable(GmailUnavailable):
    pass
