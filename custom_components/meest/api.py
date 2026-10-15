"""Minimal API client based on Meest Android 1.5.0 and local account tests."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiohttp

from .const import APP_VERSION, BASE_URL, MAX_PAGES, PAGE_SIZE


class MeestError(Exception):
    """Safe API error; never includes server bodies or credentials."""


class MeestAuthError(MeestError):
    """Credentials or session rejected."""


class MeestRateLimitError(MeestError):
    """API requested a delay."""

    def __init__(self, retry_after: int = 900) -> None:
        super().__init__("Meest rate limit")
        self.retry_after = retry_after


@dataclass(frozen=True)
class Tokens:
    """Sensitive fields excluded from repr."""

    token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float | None = None


def account_id(result: dict[str, Any], login: str) -> str:
    """Prefer the server identity; normalize phone login for the fallback."""
    global_id = result.get("globalUserId")
    if isinstance(global_id, str) and global_id.strip():
        return global_id.strip()
    normalized = login.strip().lower()
    if all(char.isdigit() or char in "+ -()" for char in normalized):
        normalized = "".join(char for char in normalized if char.isdigit())
    return "login_" + hashlib.sha256(normalized.encode()).hexdigest()


def parse_tokens(result: Any) -> Tokens:
    if not isinstance(result, dict):
        raise MeestError("Unexpected authentication result")
    access, refresh = result.get("token"), result.get("refreshToken")
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise MeestError("Authentication response lacks tokens")
    expiry = result.get("expiresIn")
    expires_at = None
    if type(expiry) in (int, float) and expiry > 0:
        # Local responses look like Unix timestamps. Also accept conventional TTLs.
        expires_at = float(expiry) if expiry >= 1_000_000_000 else time.time() + expiry
    return Tokens(access, refresh, expires_at)


def retry_seconds(value: str | None) -> int:
    try:
        return max(60, min(int(value or "900"), 86400))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            return max(
                60,
                min(
                    int(
                        (
                            parsedate_to_datetime(value or "") - datetime.now(timezone.utc)
                        ).total_seconds()
                    ),
                    86400,
                ),
            )
        except (ValueError, TypeError, OverflowError):
            return 900


class MeestClient:
    """Read-only parcel client with bounded, serialized refresh."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: Tokens | None = None,
        save_tokens: Callable[[Tokens], Awaitable[None]] | None = None,
    ) -> None:
        self.session = session
        self._tokens = tokens
        self._save_tokens = save_tokens
        self._refresh_lock = asyncio.Lock()

    async def _post(self, path: str, body: dict, *, token: str | None = None) -> Any:
        operation = (
            "login"
            if path == "app/login"
            else "refresh"
            if path == "app/refreshToken"
            else "parcel request"
        )
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers.update({"token": token, "Localization": "UK"})
        try:
            async with self.session.post(
                BASE_URL + path,
                json=body,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 429:
                    raise MeestRateLimitError(retry_seconds(response.headers.get("Retry-After")))
                if response.status == 401 or (
                    response.status == 400 and path in ("app/login", "app/refreshToken")
                ):
                    raise MeestAuthError(f"Meest {operation}: HTTP {response.status}")
                if response.status != 200:
                    # A gateway/WAF 403 does not by itself prove an expired session.
                    raise MeestError(f"Meest {operation}: HTTP {response.status}")
                # Bound memory even if the server sends an unexpectedly large body.
                import json

                payload = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    payload.extend(chunk)
                    if len(payload) > 5_000_000:
                        raise MeestError("Meest response too large")
                try:
                    document = json.loads(payload)
                except (ValueError, UnicodeError):
                    raise MeestError("Meest returned invalid JSON") from None
        except (aiohttp.ClientError, TimeoutError):
            raise MeestError("Cannot connect to Meest") from None
        if not isinstance(document, dict) or "result" not in document:
            raise MeestError("Unexpected Meest response wrapper")
        if document.get("status") != "OK":
            if path == "app/login":
                raise MeestAuthError("Meest login: application rejected credentials")
            # Unknown application errors are not proof of expired credentials.
            raise MeestError(f"Meest {operation}: application error (HTTP 200)")
        return document["result"]

    async def login(self, login: str, password: str) -> tuple[str, Tokens]:
        result = await self._post(
            "app/login",
            {
                "login": login.strip(),
                "password": password,
                "osVersion": "14",
                "appVersion": APP_VERSION,
                "platform": "Android",
            },
        )
        tokens = parse_tokens(result)
        self._tokens = tokens
        return account_id(result, login), tokens

    async def _refresh(self, failed_token: str) -> None:
        async with self._refresh_lock:
            if self._tokens is None:
                raise MeestAuthError("No Meest session")
            if self._tokens.token != failed_token:
                return  # Another request already persisted the replacement tokens.
            result = await self._post(
                "app/refreshToken", {"refreshToken": self._tokens.refresh_token}
            )
            tokens = parse_tokens(result)
            self._tokens = tokens
            if self._save_tokens is not None:
                await self._save_tokens(tokens)

    async def _authenticated_post(self, path: str, body: dict) -> Any:
        if self._tokens is None:
            raise MeestAuthError("No Meest session")
        if self._tokens.expires_at is not None and self._tokens.expires_at <= time.time() + 120:
            await self._refresh(self._tokens.token)
        token = self._tokens.token
        try:
            return await self._post(path, body, token=token)
        except MeestAuthError:
            await self._refresh(token)
            return await self._post(path, body, token=self._tokens.token)

    async def parcels(self, include_business: bool = False) -> list[dict[str, Any]]:
        """Return a complete deduplicated snapshot or fail; never publish partial counts."""
        seen: dict[str, dict] = {}
        fingerprints: set[tuple[str, ...]] = set()
        expected = None
        for page in range(MAX_PAGES):
            path = (
                f"app/AllParcelAPPv2/ANDROID/{APP_VERSION}/all/{PAGE_SIZE}/{page}"
                f"?B2B={str(include_business).lower()}&B2C=true"
            )
            result = await self._authenticated_post(path, {"archiveParcels": []})
            if isinstance(result, list) and len(result) == 1:
                result = result[0]
            if not isinstance(result, dict) or not isinstance(
                result.get("parcelsForRequestedPage"), list
            ):
                raise MeestError("Unexpected parcel list structure")
            items = result["parcelsForRequestedPage"]
            count = result.get("quantitybyMode")
            if type(count) is int and count >= 0 and (items or expected is None):
                if expected is not None and expected != count:
                    raise MeestError("Parcel count changed during pagination")
                expected = count
            if not items:
                if expected is not None and len(seen) != expected:
                    raise MeestError("Incomplete parcel pagination")
                return list(seen.values())
            ids = []
            for item in items:
                if not isinstance(item, dict):
                    raise MeestError("Unexpected parcel item")
                ident = item.get("parcelID") or item.get("parcelNumber")
                if not isinstance(ident, str) or not ident:
                    raise MeestError("Parcel identity missing")
                ids.append(ident)
                seen[ident] = item
            fingerprint = tuple(sorted(ids))
            if fingerprint in fingerprints:
                raise MeestError("Repeated parcel page")
            fingerprints.add(fingerprint)
            await asyncio.sleep(1)
        raise MeestError("Parcel pagination limit reached")
