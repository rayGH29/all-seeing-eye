"""OpenAI-backed LLM provider.

The ``openai`` package is an optional dependency. Import is deferred to call
time so the rest of the tool works without it installed (use --no-llm, or a
different provider).
"""

from __future__ import annotations

from aseye.core.exceptions import LLMError
from aseye.llm.base import LLMProvider
from aseye.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from aseye.models import Report


class OpenAIProvider(LLMProvider):
    def analyze(self, report: Report) -> str:
        if not self.api_key:
            raise LLMError(
                "No OpenAI API key found. Set OPENAI_API_KEY or llm.api_key in config."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dep
            raise LLMError(
                "The 'openai' package is not installed. Install it with "
                "`pip install openai` (or `pip install .[openai]`), or run with --no-llm."
            ) from exc

        client = OpenAI(api_key=self.api_key)
        try:
            resp = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(report)},
                ],
            )
        except Exception as exc:  # noqa: BLE001 - surface provider errors uniformly
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        return (resp.choices[0].message.content or "").strip()
