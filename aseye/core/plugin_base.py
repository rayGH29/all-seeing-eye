"""The plugin contract.

Every integration (Sherlock, HaveIBeenPwned, a custom scraper, ...) is a
subclass of :class:`BasePlugin` dropped into the ``plugins/`` folder. The
registry auto-discovers subclasses; the orchestrator calls :meth:`run`.

Writing a plugin is intentionally minimal:

    from aseye.core.plugin_base import BasePlugin
    from aseye.models import RunMode, Target

    class MyPlugin(BasePlugin):
        name = "my_plugin"
        version = "1.0.0"
        description = "What it does."
        author = "you"
        supported_targets = {"username"}

        def run(self, target, mode, settings):
            return {"found": [...]}

Return any JSON-serializable dict from ``run``; the framework wraps timing,
status, and errors around it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Set

from aseye.models import RunMode, Target


class BasePlugin(ABC):
    """Base class all plugins must inherit from."""

    # ---- metadata (override in subclasses) ------------------------------------
    name: str = "unnamed"
    version: str = "0.0.0"
    description: str = ""
    author: str = ""

    #: Target kinds this plugin can handle, e.g. {"username", "email"}.
    supported_targets: Set[str] = set()

    #: Default settings applied in NORMAL mode. Merged with per-plugin config.
    default_settings: Dict[str, Any] = {}

    #: Extra/overriding settings applied in DEEP mode ("run at max settings").
    deep_settings: Dict[str, Any] = {}

    # ---- framework hooks ------------------------------------------------------

    def supports(self, target: Target) -> bool:
        """Whether this plugin should run for the given target.

        Default: run if the target's kind is in ``supported_targets`` (an empty
        set means "handles any target").
        """
        if not self.supported_targets:
            return True
        return target.kind in self.supported_targets

    def resolve_settings(self, mode: RunMode, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Compute effective settings for a run.

        Layering (later wins): ``default_settings`` -> ``deep_settings`` (only
        in DEEP mode) -> per-plugin config ``overrides``.
        """
        settings: Dict[str, Any] = dict(self.default_settings)
        if mode is RunMode.DEEP:
            settings.update(self.deep_settings)
        settings.update(overrides or {})
        return settings

    @abstractmethod
    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Investigate ``target`` and return a JSON-serializable result dict.

        Implementations should honor ``mode``: in DEEP mode, do the most
        thorough work possible (more sources, higher limits, no early exits).
        Raise on failure — the orchestrator captures it as an error result.
        """
        raise NotImplementedError
