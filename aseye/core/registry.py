"""Dynamic plugin discovery.

Plugins are discovered from several folders and merged by name:

  1. **Bundled** plugins that ship inside the package
     (``aseye/builtin_plugins/``) — installed with the tool, found from any
     working directory and any install type.
  2. The **user** drop-in folder (``~/.all-seeing-eye/plugins``), auto-created.
  3. An optional **extra** folder from ``plugins.dir`` in config.

Later folders override earlier ones by plugin ``name`` (so a user plugin can
replace a bundled one). Every ``*.py`` file is loaded in isolation; an import
error in one file never breaks discovery of the rest.
"""

from __future__ import annotations

import importlib.util
import inspect
import itertools
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from aseye.config import USER_PLUGINS_DIR, PluginsConfig
from aseye.core.plugin_base import BasePlugin
from aseye.utils.logging import get_logger

log = get_logger(__name__)

# Bundled plugins ship inside the package (sibling of aseye/core/).
BUILTIN_PLUGINS_DIR = Path(__file__).resolve().parent.parent / "builtin_plugins"

# Monotonic suffix so files with the same basename in different folders get
# distinct module names.
_module_counter = itertools.count()


def _iter_plugin_files(plugins_dir: Path):
    """Yield candidate plugin files, skipping dunder/private modules."""
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        yield path


def _load_module(path: Path):
    """Import a single .py file as an isolated module object."""
    module_name = f"aseye_plugin_{next(_module_counter)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_from_dir(plugins_dir: Path) -> List[BasePlugin]:
    """Load and instantiate every plugin class defined in a directory."""
    result: List[BasePlugin] = []
    if not plugins_dir.is_dir():
        return result
    for path in _iter_plugin_files(plugins_dir):
        try:
            module = _load_module(path)
        except Exception as exc:  # noqa: BLE001 — isolate bad plugins
            log.error("Failed to import plugin %s: %s", path, exc)
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BasePlugin) or obj is BasePlugin:
                continue
            # Only take classes defined in this module (not imported bases).
            if obj.__module__ != module.__name__:
                continue
            try:
                result.append(obj())
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to instantiate plugin %s: %s", obj.__name__, exc)
    return result


@lru_cache(maxsize=1)
def _ensure_user_dir() -> Path:
    """Create (once per process) and return the user drop-in plugins folder."""
    user_dir = Path(USER_PLUGINS_DIR).expanduser()
    try:
        user_dir.mkdir(parents=True, exist_ok=True)  # give the user a place to drop plugins
    except OSError as exc:
        log.debug("Could not create user plugins dir %s: %s", user_dir, exc)
    return user_dir


def _plugin_dirs(cfg: PluginsConfig) -> List[Path]:
    """Ordered plugin folders: bundled, then user, then the optional config dir."""
    dirs = [BUILTIN_PLUGINS_DIR, _ensure_user_dir()]
    if cfg.dir:
        dirs.append(Path(cfg.dir).expanduser())
    return dirs


def discover(plugins_config: PluginsConfig, *, apply_filters: bool = True) -> List[BasePlugin]:
    """Discover and instantiate plugins from all folders, merged by name.

    With ``apply_filters`` (default), applies the config allowlist (``enabled``)
    and denylist (``disabled``). Pass ``apply_filters=False`` to get every
    discovered plugin regardless of on/off state (used to show ON/OFF status).
    """
    by_name: Dict[str, BasePlugin] = {}
    for plugins_dir in _plugin_dirs(plugins_config):
        for plugin in _load_from_dir(plugins_dir):
            by_name[plugin.name] = plugin  # later folders (user/config) win

    plugins = list(by_name.values())
    if not apply_filters:
        return plugins
    return _apply_filters(plugins, plugins_config)


def _apply_filters(plugins: List[BasePlugin], cfg: PluginsConfig) -> List[BasePlugin]:
    allow = set(cfg.enabled)
    deny = set(cfg.disabled)
    result: List[BasePlugin] = []
    for plugin in plugins:
        if plugin.name in deny:
            continue
        if allow and plugin.name not in allow:
            continue
        result.append(plugin)
    return result
