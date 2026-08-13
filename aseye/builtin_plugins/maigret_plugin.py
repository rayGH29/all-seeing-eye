"""Maigret integration (username).

Maigret (https://github.com/soxoj/maigret) is a richer successor to Sherlock:
it checks a username across thousands of sites and can extract profile info.
This plugin runs the Maigret CLI in an isolated temp dir with a JSON report and
parses the claimed accounts out of it.

Install to enable:

    pip install maigret

Only claimed (found) accounts appear in Maigret's ``--json simple`` report, so
every entry in the parsed report is a hit.
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


class MaigretPlugin(BasePlugin):
    name = "maigret"
    version = "1.0.0"
    description = "Find a username across thousands of sites via Maigret (with profile info)."
    author = "all-seeing-eye"
    supported_targets = {"username"}
    requires_tool = "maigret"

    default_settings = {
        "top_sites": 300,        # scan this many top-ranked sites
        "request_timeout": 10,   # Maigret --timeout (per request)
        "retries": 1,
        "overall_timeout": 100,  # hard cap on the whole subprocess (seconds)
    }
    deep_settings = {
        "top_sites": 1500,
        "request_timeout": 20,
        "retries": 2,
        "overall_timeout": 110,
    }

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        runner = _find_runner("maigret")
        if runner is None:
            raise RuntimeError("Maigret not found. Install it with `pip install maigret`.")

        top_sites = int(settings.get("top_sites", 300))
        request_timeout = int(settings.get("request_timeout", 10))
        retries = int(settings.get("retries", 1))
        overall_timeout = int(settings.get("overall_timeout", 100))

        workdir = Path(tempfile.mkdtemp(prefix="aseye_maigret_"))
        truncated = False
        try:
            cmd = [
                *runner,
                target.value,
                "--json", "simple",
                "-fo", str(workdir),
                "--no-progressbar",
                "--no-color",
                "--timeout", str(request_timeout),
                "--retries", str(retries),
                "--top-sites", str(top_sites),
            ]
            try:
                subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=overall_timeout)
            except subprocess.TimeoutExpired:
                truncated = True

            found = self._parse_report(workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        return {
            "username": target.value,
            "mode": mode.value,
            "found": found,
            "found_count": len(found),
            "top_sites": top_sites,
            "truncated": truncated,
        }

    @staticmethod
    def _parse_report(workdir: Path) -> List[Dict[str, Any]]:
        reports = list(workdir.glob("report_*_simple.json"))
        if not reports:
            return []
        try:
            data = json.loads(reports[0].read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []

        found: List[Dict[str, Any]] = []
        for sitename, entry in (data or {}).items():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            found.append(
                {
                    "site": sitename,
                    "url": entry.get("url_user") or entry.get("url_main"),
                    "ids": entry.get("ids") or status.get("ids") or {},
                }
            )
        return found


def _find_runner(tool: str) -> Optional[List[str]]:
    """Locate a tool: its console script, or a `python -m` module fallback."""
    binary = shutil.which(tool)
    if binary:
        return [binary]
    if importlib.util.find_spec(tool) is not None:
        return [sys.executable, "-m", tool]
    return None
