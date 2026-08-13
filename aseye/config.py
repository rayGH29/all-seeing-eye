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


def read_bundled_data(name: str) -> str:
    """Read a text file shipped in the package's ``data/`` folder.

    Uses importlib.resources so it works for source, editable, and wheel
    installs alike (the files are packaged inside ``aseye/data/``).
    """
    from importlib.resources import files

    return files("aseye").joinpath("data").joinpath(name).read_text(encoding="utf-8")

# Per-user data directory for all-seeing-eye. One home for user state
# (config, plugins, reports, shell history, …) so features don't each invent
# their own path — and everything works the same from any directory.
USER_DATA_DIR = Path.home() / ".all-seeing-eye"

# User drop-in plugins folder, searched in addition to the bundled plugins.
# Auto-created on first discovery. Drop your own `*.py` plugins here.
USER_PLUGINS_DIR = str(USER_DATA_DIR / "plugins")

# Global config file and default reports dir, so the tool behaves identically
# from any working directory (a config.yaml in the CWD still takes precedence).
GLOBAL_CONFIG_PATH = USER_DATA_DIR / DEFAULT_CONFIG_FILENAME
DEFAULT_REPORTS_DIR = str(USER_DATA_DIR / "reports")


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


class PivotConfig(BaseModel):
    """Auto-pivot: after a run, follow strongly-linked identifiers of the
    OPPOSITE kind (email -> username, username -> email) through that kind's
    tools, in a second pass."""

    enabled: bool = True
    min_sources: int = 1     # min distinct plugins that must link the identifier
    max_targets: int = 3     # cap how many pivots a run may spawn


class OutputConfig(BaseModel):
    dir: str = DEFAULT_REPORTS_DIR
    format: str = "both"  # json | md | both


class ConcurrencyConfig(BaseModel):
    max_workers: int = 8
    timeout: int = 120


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    pivot: PivotConfig = Field(default_factory=PivotConfig)

    # Absolute path this config was loaded from (None if using pure defaults).
    source_path: Optional[str] = None


def _find_config_file(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p}")
        return p
    # A config.yaml in the current directory wins (project-local override);
    # otherwise fall back to the global ~/.all-seeing-eye/config.yaml.
    for candidate in (Path.cwd() / DEFAULT_CONFIG_FILENAME, GLOBAL_CONFIG_PATH):
        if candidate.is_file():
            return candidate
    return None


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
    dest = Path(path or config.source_path or GLOBAL_CONFIG_PATH).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(exclude={"source_path"})
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    config.source_path = str(dest)
    return dest


def init_config(dest: Optional[str] = None, *, force: bool = False) -> Path:
    """Create a `config.yaml` from the bundled example.

    Returns the path written. Raises ConfigError if it already exists and
    ``force`` is False.
    """
    dest_path = Path(dest).expanduser() if dest else GLOBAL_CONFIG_PATH
    if dest_path.exists() and not force:
        raise ConfigError(f"{dest_path} already exists (use --force to overwrite).")

    try:
        template = read_bundled_data(EXAMPLE_CONFIG_FILENAME)
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(f"Bundled example config not found: {exc}") from exc

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(template, encoding="utf-8")
    return dest_path
