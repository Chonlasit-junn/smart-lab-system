"""Maintain Backend UTC time independently of the Windows wall clock."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional


class ServerClock:
    """Anchor a server timestamp to monotonic time so clock edits do not shift logs."""

    def __init__(
        self,
        wall_clock: Optional[Callable[[], datetime]] = None,
        monotonic_clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._lock = threading.Lock()
        self._server_anchor: Optional[datetime] = None
        self._monotonic_anchor: Optional[float] = None

    def sync(self, server_time: object) -> bool:
        """Update the UTC anchor from a timezone-aware Backend timestamp."""

        try:
            if isinstance(server_time, datetime):
                parsed = server_time
            elif isinstance(server_time, str):
                parsed = datetime.fromisoformat(server_time.strip().replace("Z", "+00:00"))
            else:
                return False
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return False
            server_anchor = parsed.astimezone(timezone.utc)
            monotonic_anchor = self._monotonic_clock()
        except (OverflowError, TypeError, ValueError):
            return False

        with self._lock:
            self._server_anchor = server_anchor
            self._monotonic_anchor = monotonic_anchor
        return True

    def now_utc(self) -> datetime:
        with self._lock:
            server_anchor = self._server_anchor
            monotonic_anchor = self._monotonic_anchor
        if server_anchor is None or monotonic_anchor is None:
            return self._wall_clock().astimezone(timezone.utc)

        elapsed = max(0.0, self._monotonic_clock() - monotonic_anchor)
        return server_anchor + timedelta(seconds=elapsed)
