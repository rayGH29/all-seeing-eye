"""Configuration loading and merging.

Precedence (highest wins):
  1. Values from the YAML config file (config.yaml)
  2. Built-in defaults

The parsed config is exposed as pydantic models so the rest of the code gets
typed, validated access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from aseye.core.exceptions import ConfigError

DEFAULT_CONFIG_FILENAME = "config.yaml"
EXAMPLE_CONFIG_FILENAME = "config.example.yaml"

# User drop-in plugins folder, searched in addition to the bundled plugins.
# Auto-created on first discovery. Drop your own `*.py` plugins here.
USER_PLUGINS_DIR = str(Path.home() / ".all-seeing-eye" / "plugins")


class LLMConfig(BaseModel):
    """Local LLM settings. Insights run entirely on-machine (e.g. via Ollama);
    no data is sent to any third-party API."""

    enabled: bool = True
    provider: str = "ollama"
    model: str = "llama3.1"
    host: str = "http://localhost:11434"
    max_tokens: int = 1500
    temperature: float = 0.2
    timeout: float = 300.0


class PluginsConfig(BaseModel):
    # Optional EXTRA folder to discover plugins from (absolute, or relative to
    # CWD). The bundled plugins and the user folder (~/.all-seeing-eye/plugins)
    # are always searched regardless of this value; empty = no extra folder.
    dir: str = ""
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


def save_config(config: "Config", path: Optional[str] = None) -> Path:
    """Write ``config`` back to YAML (default: its source file or ./config.yaml).

    Used by the interactive shell to persist plugin on/off toggles.
    """
    dest = Path(path or config.source_path or DEFAULT_CONFIG_FILENAME).expanduser()
    data = config.model_dump(exclude={"source_path"})
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    config.source_path = str(dest)
    return dest


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
