
"""In-memory reliability controls for the validation gateway."""

from collections import deque
from threading import Lock
from time import monotonic
from typing import Any


class RateLimiter:
    """Allow a limited number of requests within a sliding time window."""

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()

        with self._lock:
            timestamps = self._requests.setdefault(key, deque())

            while (
                timestamps
                and now - timestamps[0] >= self.window_seconds
            ):
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                return False

            timestamps.append(now)
            return True


class IdempotencyStore:
    """Store request results to avoid duplicate in-process execution."""

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            result = self._results.get(key)
            return dict(result) if result is not None else None

    def put_if_absent(
        self,
        key: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically store a result unless the key already exists."""
        with self._lock:
            if key not in self._results:
                self._results[key] = dict(result)

            return dict(self._results[key])

    def size(self) -> int:
        with self._lock:
            return len(self._results)
