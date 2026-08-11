"""Enable `python -m aseye` as an entry point equivalent to the `aseye` script."""

from aseye.cli import app

if __name__ == "__main__":
    app()
