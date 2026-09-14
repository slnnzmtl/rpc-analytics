"""In-memory IP-hash token bucket. Does not persist IPs or hashes."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    def __init__(
        self,
        *,
        capacity: float,
        refill_per_second: float,
        salt_seed: str,
    ) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.salt_seed = salt_seed
        self._buckets: dict[str, _Bucket] = {}
        self._salt_day: str | None = None
        self._lock = threading.Lock()

    def _daily_salt(self, now: datetime) -> str:
        day = now.astimezone(timezone.utc).date().isoformat()
        return f"{self.salt_seed}:{day}"

    def _key(self, client_ip: str, now: datetime) -> str:
        salt = self._daily_salt(now)
        material = f"{client_ip}|{salt}".encode()
        return hashlib.sha256(material).hexdigest()

    def allow(self, client_ip: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        day = current.astimezone(timezone.utc).date().isoformat()
        with self._lock:
            if self._salt_day != day:
                # Salt rotation drops old buckets (and any prior hashes).
                self._buckets.clear()
                self._salt_day = day
            key = self._key(client_ip, current)
            bucket = self._buckets.get(key)
            ts = current.timestamp()
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=self.capacity - 1.0, updated_at=ts)
                return True
            elapsed = max(0.0, ts - bucket.updated_at)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated_at = ts
            if bucket.tokens < 1.0:
                return False
            bucket.tokens -= 1.0
            return True
