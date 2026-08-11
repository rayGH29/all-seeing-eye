"""Dynamic plugin discovery.

Loads every ``*.py`` module found in the configured plugins directory, collects
:class:`BasePlugin` subclasses, and instantiates them. Import errors are
isolated per file so one broken plugin cannot break discovery of the rest.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import List

from aseye.config import PluginsConfig
from aseye.core.plugin_base import BasePlugin
from aseye.utils.logging import get_logger

log = get_logger(__name__)


def _iter_plugin_files(plugins_dir: Path):
    """Yield candidate plugin files, skipping dunder/private modules."""
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        yield path


def _load_module(path: Path):
    """Import a single .py file as an isolated module object."""
    module_name = f"aseye_plugins_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover(plugins_config: PluginsConfig, *, apply_filters: bool = True) -> List[BasePlugin]:
    """Discover and instantiate plugins.

    With ``apply_filters`` (default), applies the config allowlist (``enabled``)
    and denylist (``disabled``) by plugin ``name`` — an empty ``enabled`` list
    means "all discovered plugins". Pass ``apply_filters=False`` to get every
    discovered plugin regardless of on/off state (used to show ON/OFF status).
    """
    plugins_dir = Path(plugins_config.dir).expanduser()
    if not plugins_dir.is_dir():
        log.warning("Plugins directory not found: %s", plugins_dir)
        return []

    discovered: List[BasePlugin] = []
    for path in _iter_plugin_files(plugins_dir):
        try:
            module = _load_module(path)
        except Exception as exc:  # noqa: BLE001 — isolate bad plugins
            log.error("Failed to import plugin %s: %s", path.name, exc)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BasePlugin) or obj is BasePlugin:
                continue
            # Only take classes defined in this module (not imported bases).
            if obj.__module__ != module.__name__:
                continue
            try:
                discovered.append(obj())
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to instantiate plugin %s: %s", obj.__name__, exc)

    if not apply_filters:
        return discovered
    return _apply_filters(discovered, plugins_config)


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
