"""Integration tests for the vault backend in the TUI app."""

from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from kanban_tui.app import KanbanTui
from kanban_tui.config import Backends
from kanban_tui.modal.modal_task_screen import ModalTaskEditScreen
from kanban_tui.widgets.task_card import TaskCard
from tests.conftest import write_task_note

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


async def focus_card(app: KanbanTui, pilot, title: str) -> TaskCard:
    card = next(c for c in app.screen.query(TaskCard) if c.task_.title == title)
    card.focus()
    await pilot.pause()
    return card


def find_card(app: KanbanTui, title: str) -> TaskCard:
    return next(c for c in app.screen.query(TaskCard) if c.task_.title == title)


async def test_pressing_a_move_key_writes_the_note(
    vault_app: KanbanTui, test_vault: Path
):
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press("L")
        await pilot.pause()

        assert find_card(vault_app, "two").task_.column == 3
        text = (test_vault / "01-Projects/Alpha/tasks/two.md").read_text()
        assert "\nstatus: active\n" in text


async def test_a_refused_move_is_shown(vault_app: KanbanTui, test_vault: Path):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")
        path.write_text(path.read_text().replace("pending", "proposed"))

        await pilot.press("L")
        await pilot.pause()

        assert any(n.title == "Status Update Failed" for n in vault_app._notifications)
        assert find_card(vault_app, "two").task_.column == 2


@pytest.mark.parametrize(
    "focused_title,expected_column",
    [("zero", 1), ("two", 2), ("one", 3), (None, 2)],
)
async def test_a_new_card_lands_in_the_focused_column(
    vault_app: KanbanTui,
    test_vault: Path,
    focused_title: str | None,
    expected_column: int,
):
    write_task_note(
        test_vault, "01-Projects/Alpha/tasks/zero.md", {"status": "proposed"}
    )
    if focused_title is None:
        for note in (test_vault / "01-Projects/Alpha/tasks").glob("*.md"):
            note.unlink()
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        if focused_title:
            await focus_card(vault_app, pilot, focused_title)
        else:
            assert not list(vault_app.screen.query(TaskCard))

        await pilot.press("n")
        await pilot.press(*"Brand new")
        await pilot.click("#btn_continue")
        await pilot.pause()

        assert find_card(vault_app, "Brand new").task_.column == expected_column
        text = (test_vault / "00-Inbox/brand-new.md").read_text()
        assert "# Brand new" in text


async def test_a_refused_creation_keeps_the_typed_input(
    vault_app: KanbanTui, test_vault: Path
):
    (test_vault / "05-Templates/task.md").unlink()
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press("n")
        await pilot.press(*"Kept title")
        await pilot.click("#btn_continue")
        await pilot.pause()

        assert any(n.severity == "error" for n in vault_app._notifications)
        assert isinstance(vault_app.screen, ModalTaskEditScreen)
        assert vault_app.screen.query_one("#input_title", Input).value == "Kept title"
        assert not list(test_vault.rglob("kept-title*.md"))
