"""Per-IP and per-email limits on login, sign-up, and demo creation.

Without them, someone could guess passwords endlessly or create thousands of demo
accounts. Counts are kept in memory, which is enough for a single server process; with
several servers they'd move to a shared store such as Redis.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    """At most `limit` hits per key in any `window_seconds`-long period (a sliding window)."""

    def __init__(
        self,
        name: str,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # sync routes run in a thread pool

    def hit(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the next one is."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window_seconds - now
            hits.append(now)
            return None

    def check(self, key: str, message: str) -> None:
        """`hit`, answering the HTTP request with a 429 when over the limit."""
        wait = self.hit(key)
        if wait is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                message,
                headers={"Retry-After": str(max(int(wait), 1))},
            )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    # Behind a load balancer this is the balancer's address unless uvicorn runs with
    # --proxy-headers (set up with deployment).
    return request.client.host if request.client else "unknown"


login_per_ip = RateLimiter("login_per_ip", limit=10, window_seconds=60)
# Slows guessing one account's password from many IPs.
login_per_email = RateLimiter("login_per_email", limit=20, window_seconds=60 * 60)
register_per_ip = RateLimiter("register_per_ip", limit=5, window_seconds=60 * 60)
demo_per_ip = RateLimiter("demo_per_ip", limit=5, window_seconds=60 * 60)

ALL_LIMITERS = [login_per_ip, login_per_email, register_per_ip, demo_per_ip]
