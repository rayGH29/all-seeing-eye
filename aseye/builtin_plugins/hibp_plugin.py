"""Have I Been Pwned (HIBP) integration.

Checks an email address against the HIBP v3 API for known data breaches (and,
in deep mode, pastes). The breach/paste account endpoints require an API key:

    https://haveibeenpwned.com/API/Key

Provide the key via per-plugin config (``plugins.settings.hibp.api_key``) or the
``HIBP_API_KEY`` environment variable (env wins). If no key is available the
plugin raises a clear error, which the orchestrator records as a failed result
while other plugins keep running.

Modes:
- NORMAL: truncated breach list (names only), verified breaches only.
- DEEP:   full breach detail, include unverified breaches, and fetch pastes.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

_API_BASE = "https://haveibeenpwned.com/api/v3"
# HIBP rejects requests without a descriptive User-Agent.
_USER_AGENT = "all-seeing-eye-osint-tool"


class HibpPlugin(BasePlugin):
    name = "hibp"
    version = "1.0.0"
    description = "Check an email against Have I Been Pwned breaches (and pastes in deep mode)."
    author = "all-seeing-eye"
    supported_targets = {"email"}  # HIBP account lookups are keyed by email.
    requires_key_env = "HIBP_API_KEY"
    requires_key_setting = "api_key"

    default_settings = {
        "api_key": "",             # falls back to $HIBP_API_KEY
        "truncate": True,          # names-only breach list
        "include_pastes": False,
        "include_unverified": False,
        "timeout": 30,             # per-request timeout (seconds)
        "max_retries": 3,          # retries on rate-limit / transient errors
        "rate_limit": 1.6,         # min seconds between HIBP requests (be polite)
    }
    deep_settings = {
        "truncate": False,         # full breach detail
        "include_pastes": True,
        "include_unverified": True,
    }

    # ---- main entry point -----------------------------------------------------

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        api_key = os.environ.get("HIBP_API_KEY") or settings.get("api_key") or ""
        if not api_key:
            raise RuntimeError(
                "No HIBP API key. Set the HIBP_API_KEY environment variable or "
                "plugins.settings.hibp.api_key in config. Get one at "
                "https://haveibeenpwned.com/API/Key"
            )

        truncate = bool(settings.get("truncate", True))
        include_unverified = bool(settings.get("include_unverified", False))
        include_pastes = bool(settings.get("include_pastes", False))
        timeout = float(settings.get("timeout", 30))
        max_retries = int(settings.get("max_retries", 3))
        rate_limit = float(settings.get("rate_limit", 1.6))

        account = quote(target.value, safe="")
        headers = {"hibp-api-key": api_key, "user-agent": _USER_AGENT}

        result: Dict[str, Any] = {"account": target.value, "mode": mode.value}
        with httpx.Client(headers=headers, timeout=timeout) as client:
            breaches_raw = self._get_account(
                client,
                f"breachedaccount/{account}",
                params={
                    "truncateResponse": "true" if truncate else "false",
                    "includeUnverified": "true" if include_unverified else "false",
                },
                max_retries=max_retries,
                rate_limit=rate_limit,
            )
            breaches = [self._normalize_breach(b, truncate) for b in (breaches_raw or [])]
            result["breach_count"] = len(breaches)
            result["breaches"] = breaches

            if include_pastes:
                pastes_raw = self._get_account(
                    client,
                    f"pasteaccount/{account}",
                    params=None,
                    max_retries=max_retries,
                    rate_limit=rate_limit,
                )
                pastes = [self._normalize_paste(p) for p in (pastes_raw or [])]
                result["paste_count"] = len(pastes)
                result["pastes"] = pastes

        return result

    # ---- HTTP ----------------------------------------------------------------

    def _get_account(
        self,
        client: httpx.Client,
        path: str,
        params: Optional[Dict[str, str]],
        max_retries: int,
        rate_limit: float = 0.0,
    ) -> Optional[List[Dict[str, Any]]]:
        """GET an HIBP account endpoint, handling HIBP's status-code semantics.

        Returns the parsed JSON list, or ``None`` for 404 (account not found in
        this dataset). Retries on 429/transient errors up to ``max_retries``.
        Raises RuntimeError on auth or other unrecoverable errors.
        """
        url = f"{_API_BASE}/{path}"
        attempt = 0
        while True:
            self.throttle("hibp", rate_limit)
            try:
                resp = client.get(url, params=params)
            except httpx.TransportError as exc:
                if attempt >= max_retries:
                    raise RuntimeError(f"HIBP request failed: {exc}") from exc
                time.sleep(self._backoff(attempt))
                attempt += 1
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None  # no breaches/pastes for this account
            if resp.status_code == 429:
                if attempt >= max_retries:
                    raise RuntimeError("HIBP rate limit exceeded (429) after retries.")
                retry_after = self._retry_after_seconds(resp, attempt)
                time.sleep(retry_after)
                attempt += 1
                continue
            if resp.status_code == 401:
                raise RuntimeError("HIBP rejected the API key (401 Unauthorized).")
            if resp.status_code == 403:
                raise RuntimeError("HIBP forbade the request (403) — check the User-Agent/key.")
            raise RuntimeError(f"HIBP returned unexpected status {resp.status_code}.")

    @staticmethod
    def _retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
        """Prefer HIBP's Retry-After header; otherwise exponential backoff."""
        header = resp.headers.get("retry-after")
        if header:
            try:
                return min(float(header), 60.0)
            except ValueError:
                pass
        return HibpPlugin._backoff(attempt)

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0 ** attempt, 30.0)

    # ---- normalization -------------------------------------------------------

    @staticmethod
    def _normalize_breach(item: Dict[str, Any], truncate: bool) -> Dict[str, Any]:
        """Map HIBP's PascalCase breach object to a stable snake_case subset."""
        if truncate:
            # Truncated responses contain only {"Name": "..."}.
            return {"name": item.get("Name")}
        return {
            "name": item.get("Name"),
            "title": item.get("Title"),
            "domain": item.get("Domain"),
            "breach_date": item.get("BreachDate"),
            "added_date": item.get("AddedDate"),
            "pwn_count": item.get("PwnCount"),
            "data_classes": item.get("DataClasses"),
            "is_verified": item.get("IsVerified"),
            "is_sensitive": item.get("IsSensitive"),
            "description": item.get("Description"),
        }

    @staticmethod
    def _normalize_paste(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": item.get("Source"),
            "id": item.get("Id"),
            "title": item.get("Title"),
            "date": item.get("Date"),
            "email_count": item.get("EmailCount"),
        }
