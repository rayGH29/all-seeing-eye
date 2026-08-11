"""Build an :class:`LLMProvider` from configuration.

Only local providers are supported — nothing is sent to a third-party API.
"""

from __future__ import annotations

from aseye.config import LLMConfig
from aseye.core.exceptions import LLMError
from aseye.llm.base import LLMProvider
from aseye.llm.ollama_provider import OllamaProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
}


def build_provider(cfg: LLMConfig) -> LLMProvider:
    """Instantiate the provider named in ``cfg.provider``."""
    provider_cls = _PROVIDERS.get(cfg.provider.lower())
    if provider_cls is None:
        raise LLMError(
            f"Unknown LLM provider '{cfg.provider}'. "
            f"Available: {', '.join(sorted(_PROVIDERS))}."
        )
    return provider_cls(
        model=cfg.model,
        host=cfg.host,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout,
    )
