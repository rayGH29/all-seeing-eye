"""Startup banner: the ASCII eye (from ascii-eye.txt) in red, with the name."""

from __future__ import annotations

from pathlib import Path

from aseye import __version__
from aseye.utils.logging import console

_ART_FILENAME = "ascii-eye.txt"

# Used only if ascii-eye.txt can't be found (e.g. an installed copy without it).
_FALLBACK = r"""
      ___________
    /             \
   /    .-----.    \
  |    | ( O ) |    |
   \    '-----'    /
    \             /
      '---------'
"""


def _load_art() -> str:
    """Read the eye art from ascii-eye.txt, searching the repo root and CWD."""
    for candidate in (
        Path(__file__).resolve().parents[2] / _ART_FILENAME,  # repo root (running from source)
        Path.cwd() / _ART_FILENAME,
    ):
        try:
            if candidate.is_file():
                return _trim_blank_lines(candidate.read_text(encoding="utf-8"))
        except OSError:
            pass
    return _trim_blank_lines(_FALLBACK)


def _trim_blank_lines(text: str) -> str:
    """Drop leading/trailing whitespace-only lines (keeps internal shape)."""
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def print_banner() -> None:
    """Print the red eye + name/version. Called at the start of a run."""
    art = _load_art()
    width = max((len(line) for line in art.splitlines()), default=0)

    console.print(art, style="bold red", markup=False, highlight=False, soft_wrap=True)
    name = "A L L - S E E I N G - E Y E".center(width)
    version = f"v{__version__}".center(width)
    console.print(name, style="bold red", markup=False, highlight=False, soft_wrap=True)
    console.print(f"{version}\n", style="red dim", markup=False, highlight=False, soft_wrap=True)
