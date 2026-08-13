"""Command-line interface for all-seeing-eye (Typer + Rich).

Usage examples:
    aseye run johndoe --no-llm
    aseye deep-research johndoe
    aseye run a@b.com --plugins sherlock --format md
    aseye plugins list
    aseye config init
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from aseye import __version__
from aseye.config import (
    GLOBAL_CONFIG_PATH,
    USER_PLUGINS_DIR,
    Config,
    init_config,
    load_config,
    save_config,
)
from aseye.core import orchestrator, registry
from aseye.core.exceptions import AseyeError
from aseye.models import PluginStatus, RunMode
from aseye.utils.banner import print_banner
from aseye.utils.logging import console, setup_logging

_PLUGIN_TEMPLATE = '''\
"""{name} plugin for all-seeing-eye."""

from __future__ import annotations

from typing import Any, Dict

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target


class {class_name}(BasePlugin):
    name = "{slug}"
    version = "0.1.0"
    description = "TODO: describe what this plugin does."
    author = "you"
    supported_targets = {{"username"}}   # or {{"email"}}, or both

    # Settings per mode; deep only lists the differences.
    default_settings = {{"limit": 10}}    # NORMAL (aseye run)
    deep_settings = {{"limit": 100}}      # DEEP   (aseye deep-research)

    # Optional: declared for `aseye doctor` readiness checks.
    # requires_tool = "some_cli_or_module"
    # requires_key_env = "SOME_API_KEY"
    # requires_key_setting = "api_key"

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        # target.value = the username/email; target.kind = "username"/"email"
        # Return any JSON-serializable dict; raise on failure.
        return {{"target": target.value, "mode": mode.value, "limit": settings["limit"]}}
'''

app = typer.Typer(
    help="all-seeing-eye — modular local OSINT with LLM-driven insights.",
    add_completion=True,
)
plugins_app = typer.Typer(help="Inspect available plugins.", no_args_is_help=True)
config_app = typer.Typer(help="Manage configuration.", no_args_is_help=True)
app.add_typer(plugins_app, name="plugins")
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"all-seeing-eye {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    _version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    setup_logging(verbose=verbose)
    # No subcommand -> launch the interactive shell ("mini app").
    if ctx.invoked_subcommand is None:
        from aseye.shell import run_shell

        run_shell(verbose=verbose)


def _parse_plugins_option(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _execute(
    target: str,
    mode: RunMode,
    config_path: Optional[str],
    plugins: Optional[str],
    no_llm: bool,
    output: Optional[str],
    fmt: Optional[str],
    no_pivot: bool = False,
) -> None:
    """Shared body for the one-shot `run` and `deep-research` commands."""
    print_banner()
    try:
        config = load_config(config_path)
    except AseyeError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    if output:
        config.output.dir = output

    try:
        outcome = run_target(
            config,
            target,
            mode,
            only=_parse_plugins_option(plugins),
            use_llm=not no_llm,
            output_format=fmt,
            pivot=not no_pivot,
        )
    except AseyeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    _print_summary(outcome, config)


def run_target(
    config: Config,
    target: str,
    mode: RunMode,
    *,
    only: Optional[List[str]] = None,
    use_llm: bool = True,
    output_format: Optional[str] = None,
    show_progress: bool = True,
    pivot: bool = True,
) -> orchestrator.RunOutcome:
    """Banner-free, no-exit run used by both the CLI and the interactive shell.

    Raises :class:`AseyeError` on failure (callers decide how to present it).
    """
    return orchestrator.run(
        config,
        target,
        mode=mode,
        only=only,
        use_llm=use_llm,
        output_format=output_format,
        show_progress=show_progress,
        pivot=pivot,
    )


def _print_summary(outcome: orchestrator.RunOutcome, config: Config) -> None:
    report = outcome.report
    table = Table(title=f"OSINT run — {report.target.value} ({report.target.kind})")
    table.add_column("Plugin", style="cyan")
    table.add_column("Status")
    table.add_column("Time", justify="right")

    status_styles = {
        PluginStatus.SUCCESS: "green",
        PluginStatus.ERROR: "red",
        PluginStatus.TIMEOUT: "yellow",
        PluginStatus.SKIPPED: "dim",
    }
    for res in report.results:
        style = status_styles.get(res.status, "white")
        dur = f"{res.duration_seconds:.2f}s" if res.duration_seconds is not None else "-"
        table.add_row(res.plugin, f"[{style}]{res.status.value}[/{style}]", dur)

    console.print(table)

    if not report.results:
        console.print("[yellow]No plugins ran for this target.[/yellow]")

    for pivot in report.pivots:
        ok = sum(1 for r in pivot.results if r.status == PluginStatus.SUCCESS)
        console.print(
            f"[magenta]↳ pivot[/magenta] {pivot.kind} [bold]{pivot.target}[/bold] "
            f"— {ok}/{len(pivot.results)} plugin(s) succeeded"
        )

    if report.insights:
        console.print(Panel(report.insights, title="AI Insights", border_style="magenta"))

    for path in outcome.written_paths:
        console.print(f"[green]Wrote[/green] {path}")


@app.command()
def run(
    target: str = typer.Argument(..., help="Username or email to investigate."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
    plugins: Optional[str] = typer.Option(None, "--plugins", "-p", help="Comma-separated plugin names to run."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip the LLM insights step."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory override."),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="Report format: json | md | both."),
    no_pivot: bool = typer.Option(False, "--no-pivot", help="Don't auto-pivot to linked identifiers."),
) -> None:
    """Run a normal OSINT sweep of TARGET."""
    _execute(target, RunMode.NORMAL, config_path, plugins, no_llm, output, fmt, no_pivot)


@app.command(name="deep-research")
def deep_research(
    target: str = typer.Argument(..., help="Username or email to investigate."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
    plugins: Optional[str] = typer.Option(None, "--plugins", "-p", help="Comma-separated plugin names to run."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip the LLM insights step."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory override."),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="Report format: json | md | both."),
    no_pivot: bool = typer.Option(False, "--no-pivot", help="Don't auto-pivot to linked identifiers."),
) -> None:
    """Run every plugin at its MAXIMUM settings (deep research mode)."""
    _execute(target, RunMode.DEEP, config_path, plugins, no_llm, output, fmt, no_pivot)


def _tool_ready(tool: Optional[str]) -> Optional[bool]:
    """True/False if a required tool is present; None if the plugin needs none."""
    if not tool:
        return None
    if shutil.which(tool):
        return True
    try:
        return importlib.util.find_spec(tool) is not None
    except (ImportError, ValueError):
        return False


def _key_ready(plugin, config: Config) -> Optional[bool]:
    """True/False if a required key is available; None if the plugin needs none."""
    env = getattr(plugin, "requires_key_env", None)
    setting = getattr(plugin, "requires_key_setting", None)
    if not env and not setting:
        return None
    value = os.environ.get(env) if env else None
    if not value and setting:
        value = (config.plugins.settings.get(plugin.name) or {}).get(setting)
    return bool(value)


def _status_cell(state: Optional[bool], ok_text: str, bad_text: str) -> str:
    if state is None:
        return "[dim]—[/dim]"
    return f"[green]{ok_text}[/green]" if state else f"[red]{bad_text}[/red]"


# ---- per-plugin settings editing (shared by CLI + shell) ---------------------

def find_plugin(config: Config, name: str):
    """Return the discovered plugin instance with this name, or None."""
    for plugin in registry.discover(config.plugins, apply_filters=False):
        if plugin.name == name:
            return plugin
    return None


def _coerce(default: object, raw: str):
    """Coerce a string value to match the type of the plugin's default."""
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    if isinstance(default, list):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def set_plugin_setting(config: Config, name: str, mode: str, key: str, raw: str):
    """Set a plugin's per-mode setting (only keys the plugin defines). Persists."""
    mode = mode.lower()
    if mode not in ("normal", "deep"):
        raise AseyeError("mode must be 'normal' or 'deep'.")
    plugin = find_plugin(config, name)
    if plugin is None:
        raise AseyeError(f"Unknown plugin '{name}'.")
    editable = plugin.editable_settings()
    if key not in editable:
        allowed = ", ".join(sorted(editable)) or "(none)"
        raise AseyeError(f"'{key}' is not a setting of {name}. Editable: {allowed}.")
    value = _coerce(editable[key], raw)
    store = config.plugins.settings.setdefault(name, {})
    store.setdefault(mode, {})[key] = value
    save_config(config)
    return value


def reset_plugin_settings(config: Config, name: str, mode: Optional[str] = None) -> None:
    """Clear a plugin's overrides (a mode, or all). Persists."""
    store = config.plugins.settings.get(name)
    if not store:
        return
    if mode:
        store.pop(mode.lower(), None)
    else:
        store.pop("normal", None)
        store.pop("deep", None)
    save_config(config)


def render_plugin_info(config: Config, name: str) -> None:
    """Print a plugin's effective normal vs deep settings (with overrides marked)."""
    plugin = find_plugin(config, name)
    if plugin is None:
        console.print(f"[red]Unknown plugin '{name}'.[/red]")
        return
    overrides = config.plugins.settings.get(name, {})
    normal = plugin.resolve_settings(RunMode.NORMAL, overrides)
    deep = plugin.resolve_settings(RunMode.DEEP, overrides)
    overridden = set(overrides.get("normal", {})) | set(overrides.get("deep", {})) | {
        k for k in overrides if k not in ("normal", "deep")
    }

    keys = sorted(set(normal) | set(deep))
    table = Table(title=f"{name} — settings by mode")
    table.add_column("Setting", style="cyan")
    table.add_column("normal")
    table.add_column("deep")
    for key in keys:
        nv, dv = normal.get(key), deep.get(key)
        label = f"{key} *" if key in overridden else key
        dv_str = f"[yellow]{dv}[/yellow]" if nv != dv else str(dv)
        table.add_row(label, str(nv), dv_str)
    console.print(table)
    if overridden:
        console.print("[dim]* has a user override · edit with[/dim] "
                      f"[cyan]plugins set {name} <normal|deep> <key> <value>[/cyan]")
    elif keys:
        console.print(f"[dim]edit with[/dim] [cyan]plugins set {name} <normal|deep> <key> <value>[/cyan]")
    else:
        console.print("[dim]This plugin has no editable settings.[/dim]")


@app.command()
def doctor(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Check environment readiness: config, plugins, tools, keys, and the LLM."""
    render_doctor(load_config(config_path))


def render_doctor(config: Config) -> None:
    """Print the environment/plugin/LLM readiness report (shared by CLI + shell)."""
    import platform

    source = config.source_path or f"none (defaults; run `aseye config init` -> {GLOBAL_CONFIG_PATH})"
    console.print(
        Panel.fit(
            f"Python {platform.python_version()}  ·  all-seeing-eye {__version__}\n"
            f"Config: {source}\n"
            f"Reports dir: {config.output.dir}\n"
            f"User plugins: {USER_PLUGINS_DIR}",
            title="Environment",
            border_style="blue",
        )
    )

    discovered = registry.discover(config.plugins, apply_filters=False)
    enabled = {p.name for p in registry.discover(config.plugins)}

    table = Table(title="Plugin readiness")
    table.add_column("Plugin", style="cyan")
    table.add_column("Enabled")
    table.add_column("Tool")
    table.add_column("Key")
    table.add_column("Ready")
    for plugin in sorted(discovered, key=lambda p: p.name):
        on = plugin.name in enabled
        tool = _tool_ready(plugin.requires_tool)
        key = _key_ready(plugin, config)
        if not on:
            ready = "[dim]off[/dim]"
        elif tool is not False and key is not False:
            ready = "[green]ready[/green]"
        else:
            ready = "[red]blocked[/red]"
        table.add_row(
            plugin.name,
            "[green]on[/green]" if on else "[dim]off[/dim]",
            _status_cell(tool, "ok", "missing"),
            _status_cell(key, "set", "missing"),
            ready,
        )
    console.print(table)

    _report_llm_status(config)


def _report_llm_status(config: Config) -> None:
    llm = config.llm
    if not llm.enabled:
        console.print("LLM: [dim]disabled in config (runs use --no-llm behavior)[/dim]")
        return
    if llm.provider.lower() != "ollama":
        console.print(f"LLM: provider '{llm.provider}', model '{llm.model}'")
        return

    import httpx

    try:
        resp = httpx.get(f"{llm.host.rstrip('/')}/api/tags", timeout=3.0)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
    except httpx.HTTPError:
        console.print(
            f"LLM (ollama @ {llm.host}): [red]unreachable[/red] — start it with `ollama serve`."
        )
        return
    pulled = llm.model in models or any(m.split(":")[0] == llm.model for m in models)
    state = "[green]pulled[/green]" if pulled else f"[red]not pulled[/red] — run `ollama pull {llm.model}`"
    console.print(f"LLM (ollama @ {llm.host}): [green]reachable[/green]; model '{llm.model}' {state}")


@plugins_app.command("list")
def plugins_list(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """List all discovered (and enabled) plugins."""
    config = load_config(config_path)
    discovered = registry.discover(config.plugins)

    table = Table(title="Discovered plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Targets")
    table.add_column("Description")
    for plugin in discovered:
        targets = ", ".join(sorted(plugin.supported_targets)) or "any"
        table.add_row(plugin.name, plugin.version, targets, plugin.description)

    console.print(table)
    if not discovered:
        console.print("[yellow]No plugins found.[/yellow]")


@plugins_app.command("info")
def plugins_info(
    name: str = typer.Argument(..., help="Plugin name."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Show a plugin's effective normal vs deep settings."""
    render_plugin_info(load_config(config_path), name)


@plugins_app.command("set")
def plugins_set(
    name: str = typer.Argument(..., help="Plugin name."),
    mode: str = typer.Argument(..., help="Which mode: 'normal' or 'deep'."),
    key: str = typer.Argument(..., help="Setting name (must be one the plugin defines)."),
    value: str = typer.Argument(..., help="New value (type is coerced to the default's type)."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Override a plugin's setting for a mode (only settings the plugin defines)."""
    config = load_config(config_path)
    try:
        val = set_plugin_setting(config, name, mode, key, value)
    except AseyeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]set[/green] {name}.{mode}.{key} = {val!r}  [dim](saved)[/dim]")


@plugins_app.command("reset")
def plugins_reset(
    name: str = typer.Argument(..., help="Plugin name."),
    mode: Optional[str] = typer.Argument(None, help="Optional: 'normal' or 'deep' (default: both)."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Clear a plugin's setting overrides."""
    config = load_config(config_path)
    reset_plugin_settings(config, name, mode)
    console.print(f"[green]reset[/green] {name} {mode or 'overrides'}  [dim](saved)[/dim]")


@plugins_app.command("new")
def plugins_new(
    name: str = typer.Argument(..., help="Name for the new plugin, e.g. 'my_source'."),
    force: bool = typer.Option(False, "--force", help="Overwrite if the file already exists."),
) -> None:
    """Scaffold a starter plugin in your user plugins folder."""
    try:
        dest, slug = scaffold_plugin(name, force=force)
    except AseyeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Created[/green] {dest}")
    console.print(f"Edit it, then run [cyan]aseye run <target> --plugins {slug}[/cyan].")


def scaffold_plugin(name: str, *, force: bool = False):
    """Write a starter plugin to the user plugins folder. Returns (path, slug).

    Raises :class:`AseyeError` on a bad name or an existing file.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise AseyeError("Please provide a name with letters or digits.")
    class_name = "".join(part.capitalize() for part in slug.split("_")) + "Plugin"

    dest_dir = Path(USER_PLUGINS_DIR).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slug}_plugin.py"
    if dest.exists() and not force:
        raise AseyeError(f"{dest} already exists (use --force to overwrite).")

    dest.write_text(
        _PLUGIN_TEMPLATE.format(name=slug, class_name=class_name, slug=slug), encoding="utf-8"
    )
    return dest, slug


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config.yaml."),
) -> None:
    """Create a config.yaml from the bundled example."""
    try:
        path = init_config(force=force)
    except AseyeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Created[/green] {path} — edit it to add your API key and settings.")


@config_app.command("show")
def config_show(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Print the effective configuration."""
    config = load_config(config_path)
    dump = config.model_dump()
    source = config.source_path or "built-in defaults"
    console.print(Panel.fit(f"Source: {source}", border_style="blue"))
    console.print_json(data=dump)


if __name__ == "__main__":
    app()
