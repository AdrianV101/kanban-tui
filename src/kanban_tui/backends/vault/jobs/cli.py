from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import click

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.jobs.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    JobsConfig,
    load_config,
)
from kanban_tui.backends.vault.jobs.github import GhPrStates
from kanban_tui.backends.vault.jobs.pr_check import check_prs
from kanban_tui.backends.vault.jobs.runner import run_command
from kanban_tui.backends.vault.jobs.sweep import run_sweep
from kanban_tui.backends.vault.jobs.sweep_agent import (
    AgentResult,
    SweepRequest,
    run_agent,
)
from kanban_tui.config import VaultBackendSettings

config_option = click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Jobs config file.",
)


def _start(name: str) -> None:
    click.echo(f"{name} started {datetime.now().isoformat(timespec='seconds')}")


def _load(config_path: Path) -> tuple[JobsConfig, VaultBackend]:
    try:
        config = load_config(config_path)
        if not config.vault_path.is_dir():
            raise ConfigError(f"vault_path is not a folder: {config.vault_path}")
    except ConfigError as error:
        click.echo(f"vault-board: {error}", err=True)
        raise SystemExit(2) from None
    settings = VaultBackendSettings(vault_path=str(config.vault_path))
    return config, VaultBackend(settings=settings)


@click.group()
def main() -> None:
    """Scheduled jobs for the vault board."""


@main.command("pr-check")
@config_option
def pr_check(config_path: Path) -> None:
    """Move In Review cards whose pull requests have closed."""
    config, backend = _load(config_path)
    _start("pr-check")
    github = GhPrStates(config.gh_accounts, run_command)
    report = check_prs(backend, github.state, date.today())
    for note in report.done:
        click.echo(f"done: {note}")
    for note in report.reopened:
        click.echo(f"doing: {note}")
    for note, reason in report.skipped:
        click.echo(f"skip: {note}: {reason}")
    click.echo(
        f"pr-check: {len(report.done)} done, {len(report.reopened)} back to Doing, "
        f"{len(report.skipped)} skipped"
    )
    raise SystemExit(0 if report.ok else 1)


@main.command()
@config_option
def sweep(config_path: Path) -> None:
    """Turn captures and meeting action items into Proposed task notes."""
    config, backend = _load(config_path)
    _start("sweep")

    def agent(request: SweepRequest) -> AgentResult:
        return run_agent(request, config.claude_path, config.sweep_model, run_command)

    report = run_sweep(
        backend, config.state_path, agent, config.owner_name, date.today()
    )
    for note in report.created:
        click.echo(f"created: {note}")
    for title, text in report.errors.items():
        click.echo(f"error: {title}: {text}")
    click.echo(f"sweep: {len(report.created)} drafts, {len(report.errors)} errors")
    raise SystemExit(0 if report.ok else 1)
