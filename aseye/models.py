"""Core data models shared across the pipeline.

These pydantic models are the contract between plugins, the orchestrator, the
report layer, and the LLM layer. Keeping them here (dependency-free of the rest
of the package) avoids circular imports.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


TargetKind = Literal["username", "email", "unknown"]


class RunMode(str, Enum):
    """How thoroughly plugins should run.

    NORMAL -> quick default behavior.
    DEEP   -> "deep research": every plugin runs at its maximum settings.
    """

    NORMAL = "normal"
    DEEP = "deep"


class PluginStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class Target(BaseModel):
    """The subject of an investigation (a username or an email address)."""

    value: str
    kind: TargetKind = "unknown"


class PluginResult(BaseModel):
    """The outcome of running a single plugin against the target."""

    plugin: str
    status: PluginStatus
    mode: RunMode
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class Report(BaseModel):
    """The merged, cross-plugin picture of a target, plus optional LLM insights."""

    target: Target
    mode: RunMode
    generated_at: datetime = Field(default_factory=_utcnow)
    results: List[PluginResult] = Field(default_factory=list)
    insights: Optional[str] = None

    # ---- serialization helpers -------------------------------------------------

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Render a human-readable Markdown report."""
        lines: List[str] = []
        lines.append(f"# OSINT Report — `{self.target.value}`")
        lines.append("")
        lines.append(f"- **Target kind:** {self.target.kind}")
        lines.append(f"- **Mode:** {self.mode.value}")
        lines.append(f"- **Generated:** {self.generated_at.isoformat()}")
        lines.append(f"- **Plugins run:** {len(self.results)}")
        lines.append("")

        if self.insights:
            lines.append("## AI Insights")
            lines.append("")
            lines.append(self.insights.strip())
            lines.append("")

        lines.append("## Plugin Results")
        lines.append("")
        for res in self.results:
            lines.append(f"### {res.plugin} — {res.status.value}")
            if res.duration_seconds is not None:
                lines.append(f"_ran in {res.duration_seconds:.2f}s_")
            lines.append("")
            if res.error:
                lines.append(f"> **Error:** {res.error}")
                lines.append("")
            if res.data:
                lines.append("```json")
                lines.append(json.dumps(res.data, indent=2, default=str))
                lines.append("```")
            lines.append("")

        return "\n".join(lines)
