"""The pipeline: classify -> discover -> run plugins -> merge -> insights -> write."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from aseye.config import Config
from aseye.core import registry, report as report_mod
from aseye.core.plugin_base import BasePlugin
from aseye.llm import factory as llm_factory
from aseye.models import PluginResult, PluginStatus, Report, RunMode, Target
from aseye.utils.logging import console, get_logger
from aseye.utils.validators import classify_target

log = get_logger(__name__)


class RunOutcome:
    """Bundle of everything a run produces, for the CLI to present."""

    def __init__(self, report: Report, written_paths: List[Path]):
        self.report = report
        self.written_paths = written_paths


def _run_one_plugin(
    plugin: BasePlugin,
    target: Target,
    mode: RunMode,
    overrides: dict,
) -> PluginResult:
    """Execute a single plugin, wrapping timing/status/errors around it."""
    started = datetime.now(timezone.utc)
    settings = plugin.resolve_settings(mode, overrides)
    try:
        data = plugin.run(target, mode, settings)
        status = PluginStatus.SUCCESS
        error = None
        if not isinstance(data, dict):
            status = PluginStatus.ERROR
            error = f"Plugin returned {type(data).__name__}, expected dict."
            data = {}
    except Exception as exc:  # noqa: BLE001 - one plugin must never kill the run
        log.error("Plugin '%s' raised: %s", plugin.name, exc)
        data, status, error = {}, PluginStatus.ERROR, str(exc)

    return PluginResult(
        plugin=plugin.name,
        status=status,
        mode=mode,
        data=data,
        error=error,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
    )


def select_plugins(
    plugins: Sequence[BasePlugin],
    target: Target,
    only: Optional[Sequence[str]],
) -> List[BasePlugin]:
    """Filter discovered plugins to those that will actually run for this target."""
    only_set = {n.strip() for n in only} if only else None
    selected: List[BasePlugin] = []
    for plugin in plugins:
        if only_set is not None and plugin.name not in only_set:
            continue
        if not plugin.supports(target):
            log.info("Skipping '%s' (does not support %s target).", plugin.name, target.kind)
            continue
        selected.append(plugin)
    return selected


def run(
    config: Config,
    target_value: str,
    *,
    mode: RunMode = RunMode.NORMAL,
    only: Optional[Sequence[str]] = None,
    use_llm: bool = True,
    output_format: Optional[str] = None,
    show_progress: bool = False,
) -> RunOutcome:
    """Run the full OSINT pipeline for ``target_value`` and persist the report."""
    target = classify_target(target_value)
    log.info("Target '%s' classified as %s.", target.value, target.kind)

    discovered = registry.discover(config.plugins)
    to_run = select_plugins(discovered, target, only)
    log.info("Running %d plugin(s) in %s mode.", len(to_run), mode.value)

    results = _run_with_progress(to_run, target, mode, config, show_progress)

    merged = report_mod.build_report(target, mode, results)

    if use_llm and config.llm.enabled:
        _attach_insights(merged, config)
    elif use_llm and not config.llm.enabled:
        log.info("LLM disabled in config; skipping insights.")

    fmt = output_format or config.output.format
    written = report_mod.write_report(merged, config.output.dir, fmt)
    return RunOutcome(merged, written)


def _run_with_progress(
    plugins: List[BasePlugin],
    target: Target,
    mode: RunMode,
    config: Config,
    show_progress: bool,
) -> List[PluginResult]:
    """Run the plugins, optionally showing a live progress bar."""
    if not (show_progress and plugins and console.is_terminal):
        return _run_plugins_concurrently(plugins, target, mode, config)

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Running plugins ({mode.value})", total=len(plugins))
        return _run_plugins_concurrently(
            plugins, target, mode, config, on_complete=lambda: progress.advance(task)
        )


def _run_plugins_concurrently(
    plugins: List[BasePlugin],
    target: Target,
    mode: RunMode,
    config: Config,
    on_complete: Optional[Callable[[], None]] = None,
) -> List[PluginResult]:
    """Run plugins in a thread pool with a per-plugin timeout."""
    if not plugins:
        return []

    timeout = config.concurrency.timeout
    max_workers = max(1, config.concurrency.max_workers)
    results: List[PluginResult] = []

    def _mark_done() -> None:
        if on_complete is not None:
            on_complete()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_plugin = {
            pool.submit(
                _run_one_plugin,
                plugin,
                target,
                mode,
                config.plugins.settings.get(plugin.name, {}),
            ): plugin
            for plugin in plugins
        }
        pending = set(future_to_plugin)
        deadline_reached = False
        while pending and not deadline_reached:
            done, pending = wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
            if not done:
                # Nothing completed within the timeout window -> mark stragglers.
                deadline_reached = True
                break
            for fut in done:
                results.append(fut.result())
                _mark_done()

        for fut in pending:
            plugin = future_to_plugin[fut]
            fut.cancel()
            log.warning("Plugin '%s' timed out after %ss.", plugin.name, timeout)
            results.append(
                PluginResult(
                    plugin=plugin.name,
                    status=PluginStatus.TIMEOUT,
                    mode=mode,
                    error=f"Timed out after {timeout}s.",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            _mark_done()

    # Preserve the input plugin order for stable, readable reports.
    order = {p.name: i for i, p in enumerate(plugins)}
    results.sort(key=lambda r: order.get(r.plugin, 0))
    return results


def _attach_insights(report: Report, config: Config) -> None:
    """Call the configured LLM and attach insights, downgrading errors to notes."""
    try:
        provider = llm_factory.build_provider(config.llm)
        report.insights = provider.analyze(report)
        log.info("Attached LLM insights via %s.", config.llm.provider)
    except Exception as exc:  # noqa: BLE001 - insights are best-effort
        log.error("LLM insights step failed: %s", exc)
        report.insights = f"_LLM insights unavailable: {exc}_"
