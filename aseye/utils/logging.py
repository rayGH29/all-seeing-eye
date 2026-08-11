"""Rich-based logging and a shared console instance."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

# A single shared console keeps CLI output styling consistent everywhere.
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging to render through Rich.

    Call once at CLI startup. ``verbose=True`` enables DEBUG output.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=verbose)],
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
