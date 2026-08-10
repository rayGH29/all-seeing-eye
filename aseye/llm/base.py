"""LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from aseye.models import Report


class LLMProvider(ABC):
    """Abstract cloud/local LLM backend.

    Implementations turn a merged :class:`Report` into insight text. The factory
    builds the configured provider; the orchestrator calls :meth:`analyze`.
    """

    def __init__(self, *, model: str, api_key: str, max_tokens: int, temperature: float):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def analyze(self, report: Report) -> str:
        """Return Markdown insight text cross-referencing the report's findings."""
        raise NotImplementedError
