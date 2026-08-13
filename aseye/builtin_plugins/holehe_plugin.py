"""Holehe integration (email).

Holehe (https://github.com/megadose/holehe) checks whether an email address is
registered on 120+ sites (via registration / login / password-recovery probes).
This plugin runs the Holehe CLI in an isolated temp dir with ``-C`` (CSV) and
parses the CSV.

Install to enable:

    pip install holehe

Note: password-recovery probing can, on some sites, cause a recovery email to be
sent to the target. NORMAL mode disables it (``-NP``); DEEP mode enables it for
better coverage.
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


class HolehePlugin(BasePlugin):
    name = "holehe"
    version = "1.0.0"
    description = "Check which sites an email is registered on via Holehe."
    author = "all-seeing-eye"
    supported_targets = {"email"}
    requires_tool = "holehe"

    default_settings = {
        "request_timeout": 10,     # Holehe -T (per-site timeout)
        "overall_timeout": 100,    # hard cap on the whole subprocess (seconds)
        "password_recovery": False,  # NORMAL: off (avoids recovery emails)
    }
    deep_settings = {
        "request_timeout": 15,
        "overall_timeout": 110,
        "password_recovery": True,
    }

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        runner = _find_runner("holehe")
        if runner is None:
            raise RuntimeError("Holehe not found. Install it with `pip install holehe`.")

        request_timeout = int(settings.get("request_timeout", 10))
        overall_timeout = int(settings.get("overall_timeout", 100))
        password_recovery = bool(settings.get("password_recovery", False))

        cmd = [*runner, target.value, "--no-color", "--no-clear", "-C", "-T", str(request_timeout)]
        if not password_recovery:
            cmd.append("-NP")

        workdir = Path(tempfile.mkdtemp(prefix="aseye_holehe_"))
        truncated = False
        try:
            try:
                subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=overall_timeout)
            except subprocess.TimeoutExpired:
                truncated = True
            summary = self._parse_csv(workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        summary.update({"email": target.value, "mode": mode.value, "truncated": truncated})
        return summary

    @staticmethod
    def _parse_csv(workdir: Path) -> Dict[str, Any]:
        csv_files = list(workdir.glob("holehe_*_results.csv"))
        if not csv_files:
            return {"used_accounts": [], "used_count": 0, "checked_count": None, "rate_limited_count": None}

        used: List[Dict[str, Any]] = []
        checked = rate_limited = 0
        with csv_files[0].open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                checked += 1
                if (row.get("rateLimit") or "").strip() == "True":
                    rate_limited += 1
                if (row.get("exists") or "").strip() == "True":
                    used.append(
                        {
                            "site": row.get("name"),
                            "domain": row.get("domain"),
                            "method": row.get("method"),
                            "email_recovery": row.get("emailrecovery") or None,
                            "phone_number": row.get("phoneNumber") or None,
                        }
                    )
        return {
            "used_accounts": used,
            "used_count": len(used),
            "checked_count": checked,
            "rate_limited_count": rate_limited,
        }


def _find_runner(tool: str) -> Optional[List[str]]:
    """Locate a tool: its console script, or a `python -m` module fallback."""
    binary = shutil.which(tool)
    if binary:
        return [binary]
    if importlib.util.find_spec(tool) is not None:
        return [sys.executable, "-m", tool]
    return None
