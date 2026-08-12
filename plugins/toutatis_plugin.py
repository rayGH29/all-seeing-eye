"""Toutatis integration (Instagram username).

Toutatis (https://github.com/megadose/toutatis) pulls public profile data for an
Instagram account — full name, verification/business flags, follower counts,
public email/phone, and (in deep mode) the obfuscated recovery email/phone.

It needs a valid Instagram **sessionid** cookie (not an API key). Provide it via
the ``TOUTATIS_SESSIONID`` environment variable (preferred) or
``plugins.settings.toutatis.sessionid`` in config. Without it the plugin raises
a clear error, recorded as a failed result while other plugins keep running.

Install to enable:

    pip install toutatis

Modes:
- NORMAL: profile info only.
- DEEP:   also runs the recovery lookup for obfuscated email/phone.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


class ToutatisPlugin(BasePlugin):
    name = "toutatis"
    version = "1.0.0"
    description = "Instagram account OSINT via Toutatis (needs an Instagram sessionid)."
    author = "all-seeing-eye"
    supported_targets = {"username"}

    default_settings = {"sessionid": "", "advanced_lookup": False}
    deep_settings = {"advanced_lookup": True}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        session_id = os.environ.get("TOUTATIS_SESSIONID") or settings.get("sessionid") or ""
        if not session_id:
            raise RuntimeError(
                "No Instagram sessionid. Set the TOUTATIS_SESSIONID environment "
                "variable or plugins.settings.toutatis.sessionid in config."
            )

        try:
            import toutatis
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("Toutatis not installed. Install it with `pip install toutatis`.") from exc

        result: Dict[str, Any] = {"username": target.value, "mode": mode.value, "found": False}

        info = toutatis.getInfo(target.value, session_id)
        if info.get("error"):
            if str(info["error"]).lower() == "user not found":
                return result  # not an error — the account simply doesn't exist
            raise RuntimeError(f"Toutatis: {info['error']}")

        result["found"] = True
        result.update(self._extract(info.get("user") or {}))

        if settings.get("advanced_lookup"):
            result["advanced_lookup"] = self._advanced_lookup(toutatis, target.value)

        return result

    # ---- parsing --------------------------------------------------------------

    @staticmethod
    def _extract(user: Dict[str, Any]) -> Dict[str, Any]:
        """Pull a curated, stable subset out of Instagram's user object."""
        phone = None
        cc = user.get("public_phone_country_code")
        num = user.get("public_phone_number")
        if num:
            phone = f"+{cc} {num}".strip() if cc else str(num)

        return {
            "user_id": user.get("userID") or user.get("pk"),
            "full_name": user.get("full_name"),
            "is_verified": user.get("is_verified"),
            "is_private": user.get("is_private"),
            "is_business": user.get("is_business"),
            "category": user.get("category"),
            "biography": user.get("biography"),
            "external_url": user.get("external_url"),
            "follower_count": user.get("follower_count"),
            "following_count": user.get("following_count"),
            "media_count": user.get("media_count"),
            "public_email": user.get("public_email") or None,
            "public_phone": phone,
            "profile_pic_url": user.get("hd_profile_pic_url_info", {}).get("url")
            or user.get("profile_pic_url"),
        }

    @staticmethod
    def _advanced_lookup(toutatis, username: str) -> Dict[str, Any]:
        """Recovery lookup for obfuscated email/phone (best-effort)."""
        try:
            lookup = toutatis.advanced_lookup(username)
        except Exception as exc:  # noqa: BLE001 - best-effort extra
            return {"error": str(exc)}
        if lookup.get("error"):
            return {"error": lookup["error"]}
        data = lookup.get("user") or {}
        return {
            "obfuscated_email": data.get("obfuscated_email"),
            "obfuscated_phone": data.get("obfuscated_phone") or data.get("obfuscated_phone_number"),
        }
