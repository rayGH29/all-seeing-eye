"""WhatsMyName integration (username).

Checks a username across the community-maintained WhatsMyName site list
(https://github.com/WebBreacher/WhatsMyName). The data file (``wmn-data.json``)
is downloaded once and cached; each site is probed concurrently and a hit is
recorded when the response matches that site's "account exists" signature.

No key or external tool required — just network access.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from aseye.config import USER_DATA_DIR
from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

_DATA_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
_CACHE = Path(USER_DATA_DIR) / "cache" / "wmn-data.json"
_UA = "all-seeing-eye-osint-tool"


class WhatsMyNamePlugin(BasePlugin):
    name = "whatsmyname"
    version = "1.0.0"
    description = "Check a username across the WhatsMyName site list."
    author = "all-seeing-eye"
    supported_targets = {"username"}

    default_settings = {
        "max_sites": 300,       # NORMAL: scan the first N sites (0 = all)
        "request_timeout": 6,
        "workers": 20,
        "cache_days": 7,
        "data_url": _DATA_URL,
    }
    deep_settings = {"max_sites": 0, "workers": 30, "request_timeout": 8}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        sites = self._load_sites(settings)
        max_sites = int(settings.get("max_sites", 0))
        if max_sites:
            sites = sites[:max_sites]

        timeout = float(settings.get("request_timeout", 6))
        workers = max(1, int(settings.get("workers", 20)))
        found: List[Dict[str, Any]] = []
        errors = 0

        with httpx.Client(headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True) as client:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for outcome in pool.map(lambda s: self._check_site(client, s, target.value), sites):
                    if outcome is True:
                        continue  # not found
                    if outcome is None:
                        errors += 1
                    else:
                        found.append(outcome)

        return {
            "username": target.value,
            "mode": mode.value,
            "found": found,
            "found_count": len(found),
            "checked_count": len(sites),
            "error_count": errors,
        }

    # ---- site check ----------------------------------------------------------

    @staticmethod
    def _check_site(client: httpx.Client, site: Dict[str, Any], username: str):
        """Return a hit dict if found, True if not found, None on error."""
        uri = site.get("uri_check")
        if not uri:
            return None
        url = uri.replace("{account}", username)
        try:
            resp = client.get(url, headers=site.get("headers") or {})
        except httpx.HTTPError:
            return None
        e_code = site.get("e_code")
        e_string = site.get("e_string")
        exists = resp.status_code == e_code and (not e_string or e_string in resp.text)
        if exists:
            return {"site": site.get("name"), "url": url, "category": site.get("cat")}
        return True

    # ---- data loading --------------------------------------------------------

    def _load_sites(self, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = self._load_data(settings)
        sites = data.get("sites") if isinstance(data, dict) else None
        if not sites:
            raise RuntimeError("WhatsMyName data has no 'sites'.")
        return sites

    def _load_data(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        cache_days = float(settings.get("cache_days", 7))
        if _CACHE.is_file() and (time.time() - _CACHE.stat().st_mtime) < cache_days * 86400:
            try:
                return json.loads(_CACHE.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass  # fall through to re-download

        url = settings.get("data_url", _DATA_URL)
        try:
            resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            if _CACHE.is_file():  # network failed but we have a stale cache — use it
                return json.loads(_CACHE.read_text(encoding="utf-8"))
            raise RuntimeError(f"Could not fetch WhatsMyName data: {exc}") from exc

        try:
            _CACHE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
        return data
