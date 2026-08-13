"""Gravatar integration (email).

Gravatar exposes a public profile for any email whose owner created one, keyed
by the MD5 of the lowercased, trimmed address. This plugin needs no API key and
no external tool — just an HTTP request via httpx (already a dependency).

The profile's linked ``accounts`` (verified social profiles) and ``urls`` are
especially useful for the LLM cross-referencing step.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import httpx

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

_PROFILE_URL = "https://en.gravatar.com/{hash}.json"
_AVATAR_URL = "https://www.gravatar.com/avatar/{hash}"
_USER_AGENT = "all-seeing-eye-osint-tool"


class GravatarPlugin(BasePlugin):
    name = "gravatar"
    version = "1.0.0"
    description = "Look up an email's public Gravatar profile (no key required)."
    author = "all-seeing-eye"
    supported_targets = {"email"}

    default_settings = {"timeout": 15, "rate_limit": 0.0}
    deep_settings = {"timeout": 30}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        timeout = float(settings.get("timeout", 15))
        email_hash = hashlib.md5(target.value.strip().lower().encode("utf-8")).hexdigest()
        avatar_url = _AVATAR_URL.format(hash=email_hash)

        headers = {"user-agent": _USER_AGENT}
        self.throttle("gravatar", float(settings.get("rate_limit", 0.0)))
        try:
            resp = httpx.get(_PROFILE_URL.format(hash=email_hash), headers=headers, timeout=timeout,
                             follow_redirects=True)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gravatar request failed: {exc}") from exc

        result: Dict[str, Any] = {
            "email": target.value,
            "mode": mode.value,
            "hash": email_hash,
            "avatar_url": avatar_url,
            "exists": False,
        }

        if resp.status_code == 404:
            return result
        if resp.status_code != 200:
            raise RuntimeError(f"Gravatar returned unexpected status {resp.status_code}.")

        try:
            entry = (resp.json().get("entry") or [{}])[0]
        except (ValueError, AttributeError, IndexError):
            return result

        result["exists"] = True
        result["profile"] = {
            "profile_url": entry.get("profileUrl"),
            "preferred_username": entry.get("preferredUsername"),
            "display_name": entry.get("displayName"),
            "name": entry.get("name"),
            "about_me": entry.get("aboutMe"),
            "location": entry.get("currentLocation"),
        }
        result["accounts"] = self._accounts(entry)
        result["urls"] = [
            {"title": u.get("title"), "value": u.get("value")} for u in (entry.get("urls") or [])
        ]
        return result

    @staticmethod
    def _accounts(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "domain": a.get("domain"),
                "display": a.get("display"),
                "url": a.get("url"),
                "username": a.get("username"),
                "verified": a.get("verified"),
            }
            for a in (entry.get("accounts") or [])
        ]
