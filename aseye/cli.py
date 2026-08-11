"""Command-line interface for all-seeing-eye (Typer + Rich).

Usage examples:
    aseye run johndoe --no-llm
    aseye deep-research johndoe
    aseye run a@b.com --plugins sherlock --format md
    aseye plugins list
    aseye config init
"""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from aseye import __version__
from aseye.config import Config, init_config, load_config
from aseye.core import orchestrator, registry
from aseye.core.exceptions import AseyeError
from aseye.models import PluginStatus, RunMode
from aseye.utils.banner import print_banner
from aseye.utils.logging import console, setup_logging

app = typer.Typer(
    help="all-seeing-eye — modular local OSINT with LLM-driven insights.",
    add_completion=True,
    no_args_is_help=True,
)
plugins_app = typer.Typer(help="Inspect available plugins.", no_args_is_help=True)
config_app = typer.Typer(help="Manage configuration.", no_args_is_help=True)
app.add_typer(plugins_app, name="plugins")
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"all-seeing-eye {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    setup_logging(verbose=verbose)


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
) -> None:
    """Shared body for `run` and `deep-research`."""
    print_banner()
    try:
        config = load_config(config_path)
    except AseyeError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    if output:
        config.output.dir = output

    try:
        outcome = orchestrator.run(
            config,
            target,
            mode=mode,
            only=_parse_plugins_option(plugins),
            use_llm=not no_llm,
            output_format=fmt,
        )
    except AseyeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    _print_summary(outcome, config)


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
) -> None:
    """Run a normal OSINT sweep of TARGET."""
    _execute(target, RunMode.NORMAL, config_path, plugins, no_llm, output, fmt)


@app.command(name="deep-research")
def deep_research(
    target: str = typer.Argument(..., help="Username or email to investigate."),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
    plugins: Optional[str] = typer.Option(None, "--plugins", "-p", help="Comma-separated plugin names to run."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip the LLM insights step."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory override."),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="Report format: json | md | both."),
) -> None:
    """Run every plugin at its MAXIMUM settings (deep research mode)."""
    _execute(target, RunMode.DEEP, config_path, plugins, no_llm, output, fmt)


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
        console.print(f"[yellow]No plugins found in '{config.plugins.dir}'.[/yellow]")


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
