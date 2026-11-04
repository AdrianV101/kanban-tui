"""Integration tests for the vault backend in the TUI app."""

from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from textual.widgets import Select

from kanban_tui.app import KanbanTui
from kanban_tui.config import Backends
from kanban_tui.widgets.task_card import TaskCard

APP_SIZE = (150, 50)


async def test_warnings_are_shown_when_the_board_mounts(
    vault_app: KanbanTui, test_vault: Path
):
    (test_vault / "01-Projects/Alpha/tasks/broken.md").write_text(
        "---\ntype: task\nstatus: [unclosed\n---\n", encoding="utf-8"
    )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()

        messages = [n.message for n in vault_app._notifications]
        assert any("01-Projects/Alpha/tasks/broken.md" in m for m in messages)
        cards = list(vault_app.screen.query(TaskCard))
        assert {card.task_.title for card in cards} == {"one", "two"}


@pytest.mark.parametrize("problem", ["empty_path", "missing_path", "no_pyyaml"])
async def test_switching_to_an_unloadable_vault_is_refused(
    test_app: KanbanTui, test_vault: Path, monkeypatch, problem: str
):
    test_app.config.backend.vault_settings.vault_path = {
        "empty_path": "",
        "missing_path": (test_vault / "does-not-exist").as_posix(),
        "no_pyyaml": test_vault.as_posix(),
    }[problem]
    test_vault.mkdir(exist_ok=True)
    if problem == "no_pyyaml":

        def fail(name: str) -> str:
            raise PackageNotFoundError(name)

        monkeypatch.setattr("importlib.metadata.version", fail)

    async with test_app.run_test(size=APP_SIZE) as pilot:
        select = test_app.screen.query_one("#select_backend_mode", Select)
        select.value = f"   {Backends.VAULT}"
        await pilot.pause()

        assert test_app.config.backend.mode == Backends.SQLITE
        assert test_app.backend.__class__.__name__ == "SqliteBackend"
        assert any(n.severity == "warning" for n in test_app._notifications)
