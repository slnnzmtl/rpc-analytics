"""Report authorization: REPORT_TOKEN or allowlisted Supabase user JWT."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from rpc_analytics.config import Settings

logger = logging.getLogger("rpc_analytics")

_JWT_PARTS = 3
_AUTH_TIMEOUT = 5.0


@dataclass(frozen=True)
class _CacheEntry:
    email: str
    expires_at: float


class AuthVerifier:
    """Dual auth: shared report token or Supabase Auth user JWT."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._cache: dict[str, _CacheEntry] = {}

    def reporting_configured(self) -> bool:
        return bool(self._settings.report_token) or self._supabase_ready()

    def _supabase_ready(self) -> bool:
        return bool(self._settings.supabase_url and self._settings.supabase_anon_key)

    async def verify_authorization(self, authorization: str | None) -> None:
        if not self.reporting_configured():
            raise HTTPException(status_code=503, detail="reporting unavailable")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="unauthorized")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=401, detail="unauthorized")

        expected = self._settings.report_token
        if expected and secrets.compare_digest(token, expected):
            return

        if not self._looks_like_jwt(token):
            # Wrong report token that is not a JWT.
            if expected:
                raise HTTPException(status_code=403, detail="forbidden")
            raise HTTPException(status_code=401, detail="unauthorized")

        if not self._supabase_ready():
            raise HTTPException(status_code=403, detail="forbidden")

        email = await self._verify_supabase_jwt(token)
        allowed = self._settings.allowed_email_set()
        if email.lower() not in allowed:
            raise HTTPException(status_code=403, detail="forbidden")

    @staticmethod
    def _looks_like_jwt(token: str) -> bool:
        parts = token.split(".")
        return len(parts) == _JWT_PARTS and all(parts)

    @staticmethod
    def _token_cache_key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _jwt_exp(token: str) -> float | None:
        try:
            payload_b64 = token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            raw = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(raw)
            exp = payload.get("exp")
            if isinstance(exp, (int, float)):
                return float(exp)
        except (IndexError, ValueError, json.JSONDecodeError, TypeError):
            return None
        return None

    def _cache_get(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._cache[key]
                return None
            return entry.email

    def _cache_set(self, key: str, email: str, expires_at: float) -> None:
        with self._lock:
            # Bound cache size: drop expired first, then oldest if still large.
            now = time.time()
            expired = [k for k, v in self._cache.items() if v.expires_at <= now]
            for k in expired:
                del self._cache[k]
            if len(self._cache) >= 256:
                oldest = min(self._cache.items(), key=lambda kv: kv[1].expires_at)[0]
                del self._cache[oldest]
            self._cache[key] = _CacheEntry(email=email, expires_at=expires_at)

    async def _verify_supabase_jwt(self, token: str) -> str:
        key = self._token_cache_key(token)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        base = self._settings.supabase_url.rstrip("/")
        url = f"{base}/auth/v1/user"
        headers = {
            "apikey": self._settings.supabase_anon_key,
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=_AUTH_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError:
            logger.info("auth status=supabase_unreachable")
            raise HTTPException(status_code=401, detail="unauthorized") from None

        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="unauthorized")

        try:
            body = response.json()
        except ValueError:
            raise HTTPException(status_code=401, detail="unauthorized") from None

        email = body.get("email")
        if not isinstance(email, str) or not email.strip():
            raise HTTPException(status_code=401, detail="unauthorized")

        # Prefer confirmed users when the field is present.
        confirmed = body.get("email_confirmed_at")
        if confirmed is None and "confirmed_at" in body:
            confirmed = body.get("confirmed_at")
        if "email_confirmed_at" in body or "confirmed_at" in body:
            if not confirmed:
                raise HTTPException(status_code=403, detail="forbidden")

        exp = self._jwt_exp(token)
        expires_at = exp if exp is not None else time.time() + 60.0
        # Small skew so we do not serve past expiry.
        expires_at = min(expires_at, time.time() + 3600.0) - 5.0
        if expires_at > time.time():
            self._cache_set(key, email.strip(), expires_at)
        return email.strip()
