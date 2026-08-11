"""Report assembly and persistence.

Merges the per-plugin results into a single :class:`Report` and writes it to
disk in the requested format(s).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from aseye.models import PluginResult, Report, RunMode, Target


def build_report(
    target: Target,
    mode: RunMode,
    results: List[PluginResult],
) -> Report:
    """Merge plugin results into a Report (insights are attached later)."""
    return Report(target=target, mode=mode, results=results)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug or "target"


def write_report(report: Report, output_dir: str, fmt: str) -> List[Path]:
    """Write the report to ``output_dir`` in the given format.

    ``fmt`` is one of "json", "md", "both". Returns the paths written.
    Filenames embed the target and a UTC timestamp so runs don't clobber.
    """
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{_slugify(report.target.value)}_{timestamp}"

    written: List[Path] = []
    for suffix, renderer in _renderers_for(fmt):
        path = out / f"{stem}.{suffix}"
        path.write_text(renderer(report), encoding="utf-8")
        written.append(path)
    return written


def _renderers_for(fmt: str) -> List[Tuple[str, callable]]:
    fmt = (fmt or "both").lower()
    renderers: List[Tuple[str, callable]] = []
    if fmt in ("json", "both"):
        renderers.append(("json", lambda r: r.to_json()))
    if fmt in ("md", "both"):
        renderers.append(("md", lambda r: r.to_markdown()))
    if not renderers:  # unknown format -> default to both rather than nothing
        renderers = [("json", lambda r: r.to_json()), ("md", lambda r: r.to_markdown())]
    return renderers
