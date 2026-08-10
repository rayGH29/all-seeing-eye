"""Configuration loading and merging.

Precedence (highest wins):
  1. Environment variables (for secrets: OPENAI_API_KEY, ANTHROPIC_API_KEY)
  2. Values from the YAML config file (config.yaml)
  3. Built-in defaults

The parsed config is exposed as pydantic models so the rest of the code gets
typed, validated access.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from aseye.core.exceptions import ConfigError

DEFAULT_CONFIG_FILENAME = "config.yaml"
EXAMPLE_CONFIG_FILENAME = "config.example.yaml"

# Which env var holds the API key for each provider.
_PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class LLMConfig(BaseModel):
    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    max_tokens: int = 1500
    temperature: float = 0.2

    def resolved_api_key(self) -> str:
        """Return the API key, preferring the provider's environment variable."""
        env_var = _PROVIDER_ENV_KEYS.get(self.provider.lower())
        if env_var:
            env_val = os.environ.get(env_var)
            if env_val:
                return env_val
        return self.api_key


class PluginsConfig(BaseModel):
    dir: str = "plugins"
    enabled: List[str] = Field(default_factory=list)
    disabled: List[str] = Field(default_factory=list)
    settings: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class OutputConfig(BaseModel):
    dir: str = "reports"
    format: str = "both"  # json | md | both


class ConcurrencyConfig(BaseModel):
    max_workers: int = 8
    timeout: int = 120


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)

    # Absolute path this config was loaded from (None if using pure defaults).
    source_path: Optional[str] = None


def _find_config_file(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p}")
        return p
    candidate = Path.cwd() / DEFAULT_CONFIG_FILENAME
    return candidate if candidate.is_file() else None


def load_config(path: Optional[str] = None) -> Config:
    """Load configuration, merging file values over defaults.

    If no config file exists and none is given, built-in defaults are used so
    the tool still works out of the box (e.g. `plugins list`).
    """
    config_path = _find_config_file(path)
    if config_path is None:
        return Config()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping in {config_path}")

    try:
        config = Config(**raw)
    except Exception as exc:  # pydantic ValidationError, etc.
        raise ConfigError(f"Invalid config in {config_path}: {exc}") from exc

    config.source_path = str(config_path)
    return config


def init_config(dest: Optional[str] = None, *, force: bool = False) -> Path:
    """Create a `config.yaml` from the bundled example.

    Returns the path written. Raises ConfigError if it already exists and
    ``force`` is False.
    """
    dest_path = Path(dest or DEFAULT_CONFIG_FILENAME).expanduser()
    if dest_path.exists() and not force:
        raise ConfigError(f"{dest_path} already exists (use --force to overwrite).")

    example_path = Path(__file__).resolve().parent.parent / EXAMPLE_CONFIG_FILENAME
    if not example_path.is_file():
        raise ConfigError(f"Bundled example config not found at {example_path}")

    dest_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest_path
