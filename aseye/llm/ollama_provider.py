"""Ollama-backed local LLM provider.

Talks to a locally running Ollama server (https://ollama.com) over HTTP — no API
key, nothing leaves your machine. Uses ``httpx`` (already a dependency).

Setup:
    1. Install Ollama and start it (``ollama serve``; the desktop app also runs it).
    2. Pull a model, e.g. ``ollama pull llama3.1``.
    3. Set ``llm.model`` in config to that model name.
"""

from __future__ import annotations

import httpx

from aseye.core.exceptions import LLMError
from aseye.llm.base import LLMProvider
from aseye.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from aseye.models import Report


class OllamaProvider(LLMProvider):
    def analyze(self, report: Report) -> str:
        url = f"{self.host.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(report)},
            ],
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.host}. Is it running? "
                "Start it with `ollama serve` (or the Ollama app)."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        if resp.status_code == 404:
            raise LLMError(
                f"Ollama has no model '{self.model}'. Pull it first with "
                f"`ollama pull {self.model}`."
            )
        if resp.status_code != 200:
            raise LLMError(f"Ollama returned unexpected status {resp.status_code}: {resp.text[:200]}")

        try:
            return (resp.json()["message"]["content"] or "").strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Ollama response format: {exc}") from exc
