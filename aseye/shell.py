"""Interactive REPL — the all-seeing-eye "mini app".

Launched by running ``aseye`` with no subcommand. Shows the banner once, then
accepts commands (``run``, ``deep-research``, ``plugins``, ``config``, ``help``,
``exit``) directly without retyping ``aseye``.

The command logic lives in :meth:`AseyeShell.dispatch`, deliberately separate
from the prompt_toolkit input loop in :func:`run_shell`, so it can be driven and
tested without a TTY.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rich.table import Table

from aseye.config import USER_DATA_DIR, Config, load_config, save_config
from aseye.core import registry
from aseye.core.exceptions import AseyeError
from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode
from aseye.utils.banner import print_banner
from aseye.utils.logging import console

_HISTORY_FILE = USER_DATA_DIR / "history"

_HELP = [
    ("run <target> [opts]", "Run a normal sweep (opts: --no-llm, -p a,b, -o dir, -f json|md|both)"),
    ("deep-research <target>", "Run every plugin at its MAXIMUM settings (alias: deep)"),
    ("plugins", "List plugins with ON/OFF status"),
    ("plugins on|off <name>", "Enable/disable a plugin (persisted to config.yaml)"),
    ("plugins info <name>", "Show a plugin's normal vs deep settings"),
    ("plugins new <name>", "Scaffold a starter plugin in your user folder"),
    ("doctor", "Check readiness: plugins, tools, keys, and the LLM"),
    ("config", "Show the effective configuration"),
    ("help", "Show this help"),
    ("clear", "Clear the screen"),
    ("exit", "Leave the app (alias: quit)"),
]


class AseyeShell:
    """Holds shell state and dispatches commands."""

    def __init__(self, config: Config):
        self.config = config

    # ---- dispatch -------------------------------------------------------------

    def dispatch(self, line: str) -> bool:
        """Handle one command line. Returns False when the app should exit."""
        line = line.strip()
        if not line:
            return True
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            console.print(f"[red]Parse error:[/red] {exc}")
            return True

        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("exit", "quit", "q"):
            return False
        if cmd in ("help", "?"):
            self._cmd_help()
        elif cmd in ("clear", "cls"):
            console.clear()
        elif cmd == "run":
            self._cmd_run(args, RunMode.NORMAL)
        elif cmd in ("deep-research", "deep"):
            self._cmd_run(args, RunMode.DEEP)
        elif cmd == "plugins":
            self._cmd_plugins(args)
        elif cmd == "doctor":
            from aseye.cli import render_doctor

            render_doctor(self.config)
        elif cmd == "config":
            self._cmd_config()
        else:
            console.print(f"[red]Unknown command:[/red] {cmd}  (type [cyan]help[/cyan])")
        return True

    # ---- run / deep-research --------------------------------------------------

    def _cmd_run(self, args: List[str], mode: RunMode) -> None:
        try:
            target, only, no_llm, output, fmt = _parse_run_args(args)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return

        from aseye.cli import run_target, _print_summary  # lazy: avoids import cycle

        old_output_dir = self.config.output.dir
        if output:
            self.config.output.dir = output
        label = "deep-research" if mode is RunMode.DEEP else "run"
        console.print(f"[dim]{label}[/dim] [bold]{target}[/bold] …")
        try:
            outcome = run_target(
                self.config, target, mode, only=only, use_llm=not no_llm, output_format=fmt
            )
            _print_summary(outcome, self.config)
        except AseyeError as exc:
            console.print(f"[red]Error:[/red] {exc}")
        except Exception as exc:  # noqa: BLE001 - never kill the shell
            console.print(f"[red]Unexpected error:[/red] {exc}")
        finally:
            self.config.output.dir = old_output_dir

    # ---- plugins --------------------------------------------------------------

    def _cmd_plugins(self, args: List[str]) -> None:
        if not args or args[0] == "list":
            self._plugins_list()
            return
        sub = args[0].lower()
        if sub == "new":
            if len(args) < 2:
                console.print("[red]usage:[/red] plugins new <name>")
                return
            from aseye.cli import scaffold_plugin

            try:
                dest, slug = scaffold_plugin(args[1])
                console.print(f"[green]Created[/green] {dest}  (name: {slug})")
            except AseyeError as exc:
                console.print(f"[red]{exc}[/red]")
            return
        if sub in ("on", "off", "info"):
            if len(args) < 2:
                console.print(f"[red]usage:[/red] plugins {sub} <name>")
                return
            name = self._resolve_name(args[1])
            if name is None:
                return
            if sub == "info":
                self._plugins_info(name)
            else:
                self._plugins_toggle(name, enable=(sub == "on"))
        else:
            console.print("[red]usage:[/red] plugins [list | on <name> | off <name> | info <name>]")

    def _all_plugins(self) -> List[BasePlugin]:
        return sorted(
            registry.discover(self.config.plugins, apply_filters=False), key=lambda p: p.name
        )

    def _enabled_names(self) -> set:
        return {p.name for p in registry.discover(self.config.plugins)}

    def _resolve_name(self, token: str) -> Optional[str]:
        """Resolve a plugin name or 1-based index from the listing."""
        plugins = self._all_plugins()
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(plugins):
                return plugins[idx].name
            console.print(f"[red]No plugin #{token}.[/red]")
            return None
        names = {p.name for p in plugins}
        if token in names:
            return token
        console.print(f"[red]Unknown plugin '{token}'.[/red] Known: {', '.join(sorted(names))}")
        return None

    def _plugins_list(self) -> None:
        plugins = self._all_plugins()
        enabled = self._enabled_names()
        table = Table(title="Plugins")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Status")
        table.add_column("Targets")
        table.add_column("Description")
        for i, p in enumerate(plugins, 1):
            on = p.name in enabled
            status = "[green]ON[/green]" if on else "[red]OFF[/red]"
            targets = ", ".join(sorted(p.supported_targets)) or "any"
            table.add_row(str(i), p.name, status, targets, p.description)
        console.print(table)
        if not plugins:
            console.print("[yellow]No plugins found.[/yellow]")
        else:
            console.print("[dim]toggle with:[/dim] plugins on <name|#>  /  plugins off <name|#>")

    def _plugins_toggle(self, name: str, *, enable: bool) -> None:
        pc = self.config.plugins
        if enable:
            if name in pc.disabled:
                pc.disabled.remove(name)
            if pc.enabled and name not in pc.enabled:
                pc.enabled.append(name)
        else:
            if name not in pc.disabled:
                pc.disabled.append(name)
            if name in pc.enabled:
                pc.enabled.remove(name)
        try:
            path = save_config(self.config)
            state = "[green]ON[/green]" if enable else "[red]OFF[/red]"
            console.print(f"{name} -> {state}  [dim](saved to {path})[/dim]")
        except OSError as exc:
            console.print(f"[red]Could not save config:[/red] {exc}")

    def _plugins_info(self, name: str) -> None:
        plugin = next((p for p in self._all_plugins() if p.name == name), None)
        if plugin is None:
            return
        normal = plugin.resolve_settings(RunMode.NORMAL, {})
        deep = plugin.resolve_settings(RunMode.DEEP, {})
        keys = sorted(set(normal) | set(deep))
        table = Table(title=f"{name} — settings by mode")
        table.add_column("Setting", style="cyan")
        table.add_column("normal")
        table.add_column("deep")
        for k in keys:
            nv, dv = normal.get(k), deep.get(k)
            dv_str = f"[yellow]{dv}[/yellow]" if nv != dv else str(dv)
            table.add_row(k, str(nv), dv_str)
        console.print(table)
        if not keys:
            console.print("[dim]This plugin has no mode-specific settings.[/dim]")

    # ---- config ---------------------------------------------------------------

    def _cmd_config(self) -> None:
        console.print_json(data=self.config.model_dump(exclude={"source_path"}))

    def _cmd_help(self) -> None:
        table = Table(title="Commands")
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("What it does")
        for cmd, desc in _HELP:
            table.add_row(cmd, desc)
        console.print(table)


def _parse_run_args(args: List[str]) -> Tuple[str, Optional[List[str]], bool, Optional[str], Optional[str]]:
    """Parse `run`/`deep-research` arguments. Raises ValueError with usage."""
    usage = "usage: run <target> [--no-llm] [-p a,b] [-o dir] [-f json|md|both]"
    target: Optional[str] = None
    only: Optional[List[str]] = None
    no_llm = False
    output: Optional[str] = None
    fmt: Optional[str] = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--no-llm":
            no_llm = True
        elif a in ("-p", "--plugins", "-o", "--output", "-f", "--format"):
            if i + 1 >= len(args):
                raise ValueError(f"{a} needs a value. {usage}")
            i += 1
            value = args[i]
            if a in ("-p", "--plugins"):
                only = [s.strip() for s in value.split(",") if s.strip()]
            elif a in ("-o", "--output"):
                output = value
            else:
                fmt = value
        elif a.startswith("-"):
            raise ValueError(f"unknown option '{a}'. {usage}")
        elif target is None:
            target = a
        else:
            raise ValueError(f"unexpected argument '{a}'. {usage}")
        i += 1

    if not target:
        raise ValueError(usage)
    return target, only, no_llm, output, fmt


def run_shell(*, verbose: bool = False) -> None:
    """Print the banner once and run the interactive prompt loop."""
    config = load_config(None)
    shell = AseyeShell(config)

    print_banner()
    console.print("Interactive mode — type [cyan]help[/cyan] for commands, [cyan]exit[/cyan] to quit.\n")

    # Not a TTY (piped/CI): show help and leave instead of blocking forever.
    if not sys.stdin.isatty():
        shell._cmd_help()
        return

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory

    plugin_names = {p.name: None for p in shell._all_plugins()}
    completer = NestedCompleter.from_nested_dict(
        {
            "run": None,
            "deep-research": None,
            "deep": None,
            "plugins": {
                "list": None,
                "on": plugin_names,
                "off": plugin_names,
                "info": plugin_names,
                "new": None,
            },
            "doctor": None,
            "config": None,
            "help": None,
            "clear": None,
            "exit": None,
            "quit": None,
        }
    )
    try:
        session: PromptSession = PromptSession(
            history=FileHistory(str(_HISTORY_FILE)), completer=completer
        )
    except Exception:  # noqa: BLE001 - fall back if history file can't be opened
        session = PromptSession(completer=completer)

    prompt = HTML("<ansired><b>aseye</b></ansired><b> &gt; </b>")
    while True:
        try:
            line = session.prompt(prompt)
        except KeyboardInterrupt:  # Ctrl-C cancels the current line
            continue
        except EOFError:  # Ctrl-D exits
            break
        if not shell.dispatch(line):
            break
    console.print("[dim]bye.[/dim]")
