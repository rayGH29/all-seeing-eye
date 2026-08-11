"""Exception hierarchy for all-seeing-eye.

Keeping a single base class lets the CLI catch everything the framework raises
and present it cleanly, while callers can still catch specific subclasses.
"""


class AseyeError(Exception):
    """Base class for all all-seeing-eye errors."""


class ConfigError(AseyeError):
    """Raised when configuration is missing or invalid."""


class PluginError(AseyeError):
    """Raised when a plugin fails to load or misbehaves at the framework level."""


class LLMError(AseyeError):
    """Raised when the LLM layer cannot produce insights."""
