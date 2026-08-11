"""socialscan integration (username + email).

socialscan (https://github.com/iojw/socialscan) checks whether a username or
email address is in use / available on a set of major platforms (GitHub, GitLab,
Instagram, Pinterest, Reddit, Twitter, Tumblr, Firefox). It auto-detects emails,
so this plugin handles both target kinds.

Install to enable:

    pip install socialscan
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


def _as_bool(value: Any) -> Optional[bool]:
    """socialscan's JSON encodes booleans as the strings 'True'/'False'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value == "True":
            return True
        if value == "False":
            return False
    return None


class SocialscanPlugin(BasePlugin):
    name = "socialscan"
    version = "1.0.0"
    description = "Check username/email availability on major platforms via socialscan."
    author = "all-seeing-eye"
    supported_targets = {"username", "email"}

    default_settings = {"overall_timeout": 60, "cache_tokens": False}
    deep_settings = {"overall_timeout": 90, "cache_tokens": True}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        runner = _find_runner("socialscan")
        if runner is None:
            raise RuntimeError("socialscan not found. Install it with `pip install socialscan`.")

        overall_timeout = int(settings.get("overall_timeout", 60))
        workdir = Path(tempfile.mkdtemp(prefix="aseye_socialscan_"))
        out_file = workdir / "result.json"
        truncated = False
        try:
            cmd = [*runner, target.value, "--json", str(out_file)]
            if settings.get("cache_tokens"):
                cmd.append("--cache-tokens")
            try:
                subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=overall_timeout)
            except subprocess.TimeoutExpired:
                truncated = True
            summary = self._parse_json(out_file, target.value)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        summary.update({"query": target.value, "mode": mode.value, "truncated": truncated})
        return summary

    @staticmethod
    def _parse_json(out_file: Path, query: str) -> Dict[str, Any]:
        if not out_file.is_file():
            return {"in_use": [], "available": [], "errors": [], "in_use_count": 0, "checked_count": None}
        try:
            data = json.loads(out_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {"in_use": [], "available": [], "errors": [], "in_use_count": 0, "checked_count": None}

        # The JSON is keyed by query; take this query's list (or the only list).
        entries = data.get(query)
        if entries is None and len(data) == 1:
            entries = next(iter(data.values()))
        entries = entries or []

        in_use: List[str] = []
        available: List[str] = []
        errors: List[Dict[str, str]] = []
        for e in entries:
            platform = e.get("platform")
            success = _as_bool(e.get("success"))
            avail = _as_bool(e.get("available"))
            if success is not True:
                errors.append({"platform": platform, "message": e.get("message")})
            elif avail is False:
                in_use.append(platform)
            elif avail is True:
                available.append(platform)
        return {
            "in_use": in_use,
            "available": available,
            "errors": errors,
            "in_use_count": len(in_use),
            "checked_count": len(entries),
        }


def _find_runner(tool: str) -> Optional[List[str]]:
    """Locate a tool: its console script, or a `python -m` module fallback."""
    binary = shutil.which(tool)
    if binary:
        return [binary]
    if importlib.util.find_spec(tool) is not None:
        return [sys.executable, "-m", tool]
    return None
