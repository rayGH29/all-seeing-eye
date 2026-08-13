"""Hunter.io integration (email).

Verifies an email via the Hunter.io API and, in deep mode, searches its domain
for related people/emails (useful for linking a person to colleagues/org).

Needs a Hunter API key: set ``HUNTER_API_KEY`` (preferred) or
``plugins.settings.hunter.api_key``. Free tier available at
https://hunter.io/api-keys.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

_API = "https://api.hunter.io/v2"


class HunterPlugin(BasePlugin):
    name = "hunter"
    version = "1.0.0"
    description = "Verify an email and find related people/emails via Hunter.io."
    author = "all-seeing-eye"
    supported_targets = {"email"}
    requires_key_env = "HUNTER_API_KEY"
    requires_key_setting = "api_key"

    default_settings = {
        "api_key": "",
        "timeout": 20,
        "rate_limit": 1.0,
        "domain_search": False,  # NORMAL: verify only
        "domain_limit": 10,
    }
    deep_settings = {"domain_search": True}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        api_key = os.environ.get("HUNTER_API_KEY") or settings.get("api_key") or ""
        if not api_key:
            raise RuntimeError(
                "No Hunter API key. Set the HUNTER_API_KEY environment variable or "
                "plugins.settings.hunter.api_key in config. Get one at https://hunter.io/api-keys"
            )
        timeout = float(settings.get("timeout", 20))
        self._rate_limit = float(settings.get("rate_limit", 1.0))

        result: Dict[str, Any] = {"email": target.value, "mode": mode.value}
        with httpx.Client(timeout=timeout) as client:
            verify = self._get(client, "email-verifier", {"email": target.value, "api_key": api_key})
            result.update(self._extract_verify(verify))

            if settings.get("domain_search") and "@" in target.value:
                domain = target.value.rsplit("@", 1)[-1]
                search = self._get(
                    client,
                    "domain-search",
                    {"domain": domain, "api_key": api_key, "limit": int(settings.get("domain_limit", 10))},
                )
                result["domain"] = self._extract_domain(search)
        return result

    # ---- parsing -------------------------------------------------------------

    @staticmethod
    def _extract_verify(payload: Dict[str, Any]) -> Dict[str, Any]:
        data = (payload or {}).get("data") or {}
        return {
            "status": data.get("status"),
            "result": data.get("result"),
            "score": data.get("score"),
            "disposable": data.get("disposable"),
            "webmail": data.get("webmail"),
            "accept_all": data.get("accept_all"),
            "sources": [
                {"domain": s.get("domain"), "uri": s.get("uri")} for s in (data.get("sources") or [])
            ],
        }

    @staticmethod
    def _extract_domain(payload: Dict[str, Any]) -> Dict[str, Any]:
        data = (payload or {}).get("data") or {}
        emails: List[Dict[str, Any]] = []
        for entry in data.get("emails") or []:
            emails.append(
                {
                    "value": entry.get("value"),
                    "first_name": entry.get("first_name"),
                    "last_name": entry.get("last_name"),
                    "position": entry.get("position"),
                    "type": entry.get("type"),
                }
            )
        return {"organization": data.get("organization"), "emails": emails}

    # ---- HTTP ----------------------------------------------------------------

    def _get(self, client: httpx.Client, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.throttle("hunter", getattr(self, "_rate_limit", 1.0))
        try:
            resp = client.get(f"{_API}/{path}", params=params)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Hunter request failed: {exc}") from exc

        if resp.status_code == 401:
            raise RuntimeError("Hunter rejected the API key (401).")
        if resp.status_code == 429:
            raise RuntimeError("Hunter rate limit exceeded (429).")
        if resp.status_code >= 400:
            detail = ""
            try:
                errors = resp.json().get("errors") or []
                detail = "; ".join(e.get("details", "") for e in errors)
            except ValueError:
                pass
            raise RuntimeError(f"Hunter error {resp.status_code}: {detail or resp.text[:120]}")
        return resp.json()
