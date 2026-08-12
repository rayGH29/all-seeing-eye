"""A fully-working reference plugin.

It performs no real network activity — it returns deterministic sample data so
the whole pipeline (discovery -> run -> merge -> report -> LLM) can be exercised
out of the box. Copy this file as a starting point for real integrations.
"""

from __future__ import annotations

from typing import Any, Dict

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


class ExamplePlugin(BasePlugin):
    name = "example"
    version = "1.0.0"
    description = "Reference plugin that emits sample data (no network calls)."
    author = "all-seeing-eye"
    supported_targets = {"username", "email"}

    # In NORMAL mode we "check" a small set of sources; DEEP mode widens it.
    default_settings = {"sources": ["github", "reddit"], "max_results": 5}
    deep_settings = {"sources": ["github", "reddit", "twitter", "hackernews", "keybase"],
                     "max_results": 50}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        sources = settings.get("sources", [])
        # Simulate one "hit" per configured source.
        hits = [
            {
                "source": source,
                "profile_url": f"https://{source}.example/{target.value}",
                "confidence": "high" if mode is RunMode.DEEP else "medium",
            }
            for source in sources
        ]
        return {
            "target": target.value,
            "mode": mode.value,
            "sources_checked": sources,
            "hits": hits,
            "note": "Sample data from the example plugin — replace with a real integration.",
        }
