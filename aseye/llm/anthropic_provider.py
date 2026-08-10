"""Anthropic-backed LLM provider.

The ``anthropic`` package is an optional dependency, imported lazily.
"""

from __future__ import annotations

from aseye.core.exceptions import LLMError
from aseye.llm.base import LLMProvider
from aseye.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from aseye.models import Report


class AnthropicProvider(LLMProvider):
    def analyze(self, report: Report) -> str:
        if not self.api_key:
            raise LLMError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY or llm.api_key in config."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dep
            raise LLMError(
                "The 'anthropic' package is not installed. Install it with "
                "`pip install anthropic` (or `pip install .[anthropic]`), or run with --no-llm."
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(report)}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        # Concatenate any text blocks in the response.
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "".join(parts).strip()
