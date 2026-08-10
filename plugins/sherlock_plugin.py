"""Sherlock integration — STUB.

This demonstrates the pattern for wrapping an external CLI OSINT tool
(https://github.com/sherlock-project/sherlock) as a plugin: build a command
from the run mode, invoke it via ``subprocess``, and parse the output into a
result dict.

It is intentionally NOT wired to a real Sherlock install yet — the actual
invocation is commented out and the plugin returns a clearly-marked placeholder.
Flesh out ``run`` (and set ``available``/parsing) when you install Sherlock.
"""

from __future__ import annotations

import shutil
from typing import Any, Dict

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


class SherlockPlugin(BasePlugin):
    name = "sherlock"
    version = "0.1.0"
    description = "Find usernames across social networks via the Sherlock CLI (stub)."
    author = "all-seeing-eye"
    supported_targets = {"username"}  # Sherlock hunts usernames, not emails.

    # NORMAL: fast pass with a timeout. DEEP: no per-site timeout, print all.
    default_settings = {"timeout": 10, "extra_args": []}
    deep_settings = {"timeout": 60, "extra_args": ["--print-all"]}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        # --- Real integration would look like this ---------------------------
        # binary = shutil.which("sherlock")
        # if not binary:
        #     raise RuntimeError("Sherlock not found on PATH. Install it first.")
        # cmd = [binary, target.value, "--timeout", str(settings["timeout"]),
        #        "--no-color", *settings.get("extra_args", [])]
        # proc = subprocess.run(cmd, capture_output=True, text=True,
        #                       timeout=settings["timeout"] * 50)
        # found = self._parse_sherlock_output(proc.stdout)
        # return {"found": found, "raw": proc.stdout}
        # ---------------------------------------------------------------------

        available = shutil.which("sherlock") is not None
        return {
            "status": "stub",
            "sherlock_installed": available,
            "would_run_command": [
                "sherlock",
                target.value,
                "--timeout",
                str(settings.get("timeout")),
                *settings.get("extra_args", []),
            ],
            "note": (
                "Sherlock integration is a stub. Install Sherlock and implement the "
                "subprocess call in plugins/sherlock_plugin.py to enable it."
            ),
        }

    @staticmethod
    def _parse_sherlock_output(stdout: str) -> list:
        """Parse Sherlock's '[+] Site: URL' lines into structured hits."""
        found = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[+]") and ":" in line:
                _, rest = line.split("]", 1)
                site, _, url = rest.partition(":")
                found.append({"site": site.strip(), "url": url.strip()})
        return found
