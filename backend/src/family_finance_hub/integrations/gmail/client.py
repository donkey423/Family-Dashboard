from __future__ import annotations

from typing import Any, Protocol


class GmailClient(Protocol):
    def list_messages(self, query: str, page_token: str | None = None) -> dict[str, Any]: ...
    def get_profile(self) -> dict[str, Any]: ...
    def list_history(self, start_history_id: str, page_token: str | None = None) -> dict[str, Any]: ...
    def get_message(self, message_id: str) -> dict[str, Any]: ...
    def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...


class GmailRestClient:
    base_url = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, authorized_session: Any):
        self.session = authorized_session

    def list_messages(self, query: str, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, str | int] = {"q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        return self._get(f"{self.base_url}/messages", params=params)

    def get_profile(self) -> dict[str, Any]:
        return self._get(f"{self.base_url}/profile")

    def list_history(self, start_history_id: str, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, str | int] = {"startHistoryId": start_history_id, "historyTypes": "messageAdded", "maxResults": 500}
        if page_token:
            params["pageToken"] = page_token
        return self._get(f"{self.base_url}/history", params=params)

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._get(f"{self.base_url}/messages/{message_id}", params={"format": "full"})

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        payload = self._get(f"{self.base_url}/messages/{message_id}/attachments/{attachment_id}")
        data = payload.get("data")
        if not isinstance(data, str):
            raise GmailUnavailable("Gmail 附件目前無法取得")
        return decode_base64url(data)

    def _get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.get(url, timeout=30, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status == 404 and url.endswith("/history"):
                raise GmailHistoryExpired("Gmail history cursor 已過期") from None
            raise GmailUnavailable("Gmail 目前無法連線或授權已失效") from None
        if not isinstance(payload, dict):
            raise GmailUnavailable("Gmail 回傳格式無效")
        return payload


class GmailUnavailable(Exception):
    pass


class GmailHistoryExpired(GmailUnavailable):
    pass


def decode_base64url(value: str) -> bytes:
    import base64

    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        raise GmailUnavailable("Gmail 附件格式無效") from None
