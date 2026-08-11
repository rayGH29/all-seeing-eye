"""Sherlock integration.

Wraps the Sherlock CLI (https://github.com/sherlock-project/sherlock) to hunt a
username across social networks. Sherlock is invoked as a subprocess in an
isolated temp directory with ``--csv``; the structured CSV it writes is parsed
into hits (with a stdout fallback if the run is cut short by a timeout).

Install Sherlock to enable this plugin:

    pip install sherlock-project

If Sherlock isn't found, the plugin raises a clear error which the orchestrator
records as a failed result — other plugins keep running.

Note on timeouts: this plugin's ``overall_timeout`` bounds the whole Sherlock
run and is kept under the orchestrator's per-plugin timeout
(``concurrency.timeout`` in config, default 120s) so it returns cleanly. For
very deep sweeps you may want to raise ``concurrency.timeout`` as well.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

# CSV 'exists' column values Sherlock emits.
_CLAIMED = "Claimed"    # username found on the site
_AVAILABLE = "Available"  # username not found
_UNKNOWN = "Unknown"    # could not be determined (error/timeout/blocked)


class SherlockPlugin(BasePlugin):
    name = "sherlock"
    version = "1.0.0"
    description = "Find a username across social networks via the Sherlock CLI."
    author = "all-seeing-eye"
    supported_targets = {"username"}  # Sherlock hunts usernames, not emails.

    # NORMAL: quicker per-site timeout, bounded overall run.
    # DEEP: longer per-site timeout, include NSFW sites, larger overall budget.
    default_settings = {
        "request_timeout": 15,   # Sherlock --timeout (per-site request)
        "overall_timeout": 90,   # hard cap on the whole subprocess (seconds)
        "nsfw": False,           # include NSFW sites
        "sites": [],             # limit to these sites (empty = all sites)
        "extra_args": [],        # any additional raw Sherlock CLI flags
    }
    deep_settings = {
        "request_timeout": 30,
        "overall_timeout": 110,
        "nsfw": True,
        "sites": [],
        "extra_args": [],
    }

    # ---- main entry point -----------------------------------------------------

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        runner = self._find_runner()
        if runner is None:
            raise RuntimeError(
                "Sherlock not found. Install it with `pip install sherlock-project` "
                "(provides the `sherlock` command)."
            )

        request_timeout = int(settings.get("request_timeout", 15))
        overall_timeout = int(settings.get("overall_timeout", 90))
        sites: List[str] = list(settings.get("sites") or [])
        extra_args: List[str] = list(settings.get("extra_args") or [])

        cmd = [
            *runner,
            target.value,
            "--timeout", str(request_timeout),
            "--no-color",
            "--csv",
            "--no-txt",
            "--print-all",  # so stdout has a line per site for the fallback parser
        ]
        if settings.get("nsfw"):
            cmd.append("--nsfw")
        for site in sites:
            cmd += ["--site", site]
        cmd += extra_args

        workdir = Path(tempfile.mkdtemp(prefix="aseye_sherlock_"))
        truncated = False
        stdout = ""
        try:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=overall_timeout,
                )
                stdout = proc.stdout or ""
            except subprocess.TimeoutExpired as exc:
                # Sherlock was killed; keep whatever partial stdout we captured.
                truncated = True
                stdout = exc.stdout or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", "replace")

            summary = self._parse_csv(workdir)
            if summary is None:
                # No CSV (e.g. run was cut short) -> fall back to stdout parsing.
                found = self._parse_stdout(stdout)
                summary = {
                    "found": found,
                    "found_count": len(found),
                    "checked_count": None,
                    "not_found_count": None,
                    "unknown_count": None,
                    "source": "stdout",
                }
            else:
                summary["source"] = "csv"
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        summary.update(
            {
                "username": target.value,
                "mode": mode.value,
                "truncated": truncated,
                "sites_filter": sites or "all",
                "command": cmd,
            }
        )
        return summary

    # ---- helpers --------------------------------------------------------------

    @staticmethod
    def _find_runner() -> Optional[List[str]]:
        """Locate a way to invoke Sherlock: the console script or `-m` module."""
        binary = shutil.which("sherlock")
        if binary:
            return [binary]
        for module in ("sherlock_project", "sherlock"):
            probe = subprocess.run(
                [sys.executable, "-c", f"import importlib.util,sys;"
                 f"sys.exit(0 if importlib.util.find_spec('{module}') else 1)"],
                capture_output=True,
            )
            if probe.returncode == 0:
                return [sys.executable, "-m", module]
        return None

    @staticmethod
    def _parse_csv(workdir: Path) -> Optional[Dict[str, Any]]:
        """Parse the single CSV Sherlock writes into a structured summary.

        Returns None if no CSV was produced.
        """
        csv_files = list(workdir.glob("*.csv"))
        if not csv_files:
            return None

        found: List[Dict[str, Any]] = []
        not_found = unknown = checked = 0
        with csv_files[0].open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                checked += 1
                exists = (row.get("exists") or "").strip()
                if exists == _CLAIMED:
                    found.append(
                        {
                            "site": row.get("name"),
                            "url": row.get("url_user"),
                            "http_status": row.get("http_status"),
                            "response_time_s": row.get("response_time_s"),
                        }
                    )
                elif exists == _AVAILABLE:
                    not_found += 1
                else:  # Unknown / anything else
                    unknown += 1

        return {
            "found": found,
            "found_count": len(found),
            "checked_count": checked,
            "not_found_count": not_found,
            "unknown_count": unknown,
        }

    @staticmethod
    def _parse_stdout(stdout: str) -> List[Dict[str, Any]]:
        """Fallback: parse Sherlock's '[+] Site: URL' lines into hits."""
        found: List[Dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[+]") and ":" in line:
                _, rest = line.split("]", 1)
                site, _, url = rest.partition(":")
                if url.strip():
                    found.append({"site": site.strip(), "url": url.strip()})
        return found
