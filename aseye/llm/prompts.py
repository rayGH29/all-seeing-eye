"""Prompt templates for the cross-referencing / insights step."""

from __future__ import annotations

from aseye.models import Report

SYSTEM_PROMPT = """\
You are an OSINT analyst assistant. You are given a machine-generated report that
aggregates the raw output of several OSINT tools ("plugins") run against a single
target (a username or email address).

Your job is to CROSS-REFERENCE the findings across plugins and produce concise,
actionable insights. Specifically:

- Correlate identities: link handles, profile URLs, emails, names, and locations
  that appear to belong to the same person across different sources.
- Highlight strong signals and corroborations (the same detail from multiple
  sources) and note confidence.
- Flag contradictions, anomalies, and likely false positives.
- Identify gaps and suggest concrete next investigative steps.

Rules:
- Only reason from the data provided. Do NOT invent accounts, links, or facts.
- Be explicit about uncertainty; label inferences as such.
- This is for legitimate, authorized research only. Do not provide guidance for
  harassment, stalking, or other harmful use.

Respond in clear Markdown with short sections and bullet points.
"""


def build_user_prompt(report: Report) -> str:
    """Serialize the merged report into the analysis request body."""
    return (
        f"Target: {report.target.value} (kind: {report.target.kind})\n"
        f"Run mode: {report.mode.value}\n\n"
        "Here is the aggregated plugin data as JSON:\n\n"
        "```json\n"
        f"{report.to_json()}\n"
        "```\n\n"
        "Produce your cross-referenced analysis and insights now."
    )
