"""Build an :class:`LLMProvider` from configuration."""

from __future__ import annotations

from aseye.config import LLMConfig
from aseye.core.exceptions import LLMError
from aseye.llm.anthropic_provider import AnthropicProvider
from aseye.llm.base import LLMProvider
from aseye.llm.openai_provider import OpenAIProvider

_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
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
        api_key=cfg.resolved_api_key(),
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )
