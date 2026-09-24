from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable

from sqlalchemy.orm import sessionmaker

from ...models import GmailConnection, GmailSyncState, utc_now
from .client import GmailClient
from .sync import DEFAULT_GMAIL_QUERY, GmailSyncUseCase

SYNC_INTERVAL = timedelta(minutes=30)


class GmailSyncScheduler:
    def __init__(
        self,
        session_factory: sessionmaker,
        sync_use_case: GmailSyncUseCase,
        client_factory: Callable[[], GmailClient],
        sync_lock: Lock,
        *,
        poll_interval_seconds: int = 30,
        interval: timedelta = SYNC_INTERVAL,
    ):
        self.session_factory = session_factory
        self.sync_use_case = sync_use_case
        self.client_factory = client_factory
        self.sync_lock = sync_lock
        self.poll_interval_seconds = poll_interval_seconds
        self.interval = interval

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                await asyncio.to_thread(self.run_due)

    def run_due(self) -> bool:
        if not self.sync_lock.acquire(blocking=False):
            return False
        try:
            now = utc_now()
            with self.session_factory() as session, session.begin():
                connection = session.get(GmailConnection, "gmail")
                if connection is None or not connection.auto_sync_enabled:
                    return False
                due_at = connection.next_scheduled_sync_at
                if due_at is None or _as_utc(due_at) > now:
                    return False
                connection.next_scheduled_sync_at = now + self.interval

            with self.session_factory() as session:
                self.sync_use_case.execute(session, self.client_factory(), DEFAULT_GMAIL_QUERY)
            return True
        except Exception:
            self._record_failure()
            return False
        finally:
            self.sync_lock.release()

    def _record_failure(self) -> None:
        try:
            with self.session_factory() as session, session.begin():
                state = session.get(GmailSyncState, "gmail")
                if state is None:
                    state = GmailSyncState(id="gmail")
                    session.add(state)
                state.status = "failed"
                state.last_attempt_at = utc_now()
                state.last_error_summary = "定時同步失敗，請檢查 Gmail 授權與網路"
        except Exception:
            pass


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
