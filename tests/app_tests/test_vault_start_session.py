"""Starting a Claude Code session from a vault card with `t`."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from textual.widgets import Input, Label

from kanban_tui.app import KanbanTui
from kanban_tui.backends.vault.sessions import SessionFolder, SessionFolderKind
from kanban_tui.modal.modal_session_folder_screen import ModalSessionFolderScreen
from kanban_tui.widgets.task_card import TaskCard
from tests.conftest import make_checkout, write_task_note

APP_SIZE = (150, 50)
NOTE = "01-Projects/Alpha/tasks/tackle-me.md"
REMOTE = "github.com/inspect-scope/frontend"
COLUMN_FIELDS = {
    "proposed": {"status": "pending"},
    "ready": {"status": "pending", "board": "ready"},
    "doing": {"status": "active"},
    "in-review": {"status": "active", "board": "in-review"},
    "done": {"status": "done"},
}


async def focus_card(app: KanbanTui, pilot, title: str) -> TaskCard:
    card = next(c for c in app.screen.query(TaskCard) if c.task_.title == title)
    card.focus()
    await pilot.pause()
    return card


def errors(app: KanbanTui) -> list[str]:
    return [n.message for n in app._notifications if n.severity == "error"]


def modal_text(app: KanbanTui) -> str:
    return " ".join(str(label.render()) for label in app.screen.query(Label))


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str, str]]:
    calls: list[tuple[Path, str, str]] = []

    def record(app, folder: Path, title: str, note_path: str) -> bool:
        calls.append((folder, title, note_path))
        return True

    monkeypatch.setattr("kanban_tui.widgets.task_card.launch_session", record)
    return calls


@pytest.fixture
def card_app(vault_app: KanbanTui, test_vault: Path) -> KanbanTui:
    write_task_note(test_vault, NOTE, {"status": "pending", "board": "ready"})
    return vault_app


def answer(app: KanbanTui, monkeypatch, folder: SessionFolder) -> None:
    monkeypatch.setattr(app.backend, "session_folder", lambda task: folder)


@pytest.mark.parametrize(
    ("column", "listed"),
    [
        ("proposed", True),
        ("ready", True),
        ("doing", True),
        ("in-review", False),
        ("done", False),
    ],
)
async def test_t_is_listed_only_on_unfinished_vault_cards(
    vault_app: KanbanTui, test_vault: Path, column: str, listed: bool
):
    write_task_note(test_vault, NOTE, COLUMN_FIELDS[column])

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "tackle-me")

        assert ("t" in vault_app.screen.active_bindings) is listed


async def test_t_is_not_listed_on_sqlite_cards(test_app: KanbanTui):
    async with test_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(test_app, pilot, "Task_ready_0")

        assert "t" not in test_app.screen.active_bindings


async def test_t_on_a_linked_card_launches_in_its_checkout(
    card_app: KanbanTui, monkeypatch, launches, tmp_path: Path
):
    checkout = tmp_path / "frontend"
    answer(
        card_app,
        monkeypatch,
        SessionFolder(
            SessionFolderKind.LINKED, "Alpha", "~/Projects", checkout, (REMOTE,)
        ),
    )

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")

        await pilot.press("t")
        await pilot.pause()

        assert launches == [(checkout, "tackle-me", NOTE)]
        assert errors(card_app) == []


@pytest.mark.parametrize("kind", ["not-here", "several"])
async def test_t_on_a_card_that_cannot_start_shows_why(
    card_app: KanbanTui, monkeypatch, launches, kind: str
):
    matches = (Path("/Users/me/Projects/a"), Path("/Users/me/Projects/b"))
    folder = (
        SessionFolder(
            SessionFolderKind.NOT_HERE, "Alpha", "~/Projects", None, (REMOTE,)
        )
        if kind == "not-here"
        else SessionFolder(
            SessionFolderKind.SEVERAL, "Alpha", "~/Projects", None, (REMOTE,), matches
        )
    )
    answer(card_app, monkeypatch, folder)

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")

        await pilot.press("t")
        await pilot.pause()

        [message] = errors(card_app)
        assert REMOTE in message
        if kind == "not-here":
            assert "~/Projects" in message
        else:
            assert all(match.as_posix() in message for match in matches)
        assert launches == []


@pytest.mark.parametrize(
    ("kind", "project", "hinted"),
    [
        (SessionFolderKind.NO_LINK, "Alpha", True),
        (SessionFolderKind.NO_PROJECT, None, False),
    ],
)
async def test_t_on_an_unlinked_card_asks_for_a_folder(
    card_app: KanbanTui, monkeypatch, launches, kind, project, hinted: bool
):
    answer(card_app, monkeypatch, SessionFolder(kind, project, "~/Projects"))

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")

        await pilot.press("t")
        await pilot.pause()

        assert isinstance(card_app.screen, ModalSessionFolderScreen)
        text = modal_text(card_app)
        assert ("/vault-pkm:init-project" in text) is hinted
        if hinted:
            assert "Alpha" in text
        assert launches == []


@pytest.mark.parametrize(
    ("root", "expected"),
    [("~/root", ["~/root/a", "~/root/b"]), ("~no-such-user-xyz/root", [])],
    ids=["readable", "unknown-user"],
)
async def test_the_folder_question_suggests_the_folders_under_the_root(
    card_app: KanbanTui,
    monkeypatch,
    launches,
    tmp_path: Path,
    root: str,
    expected: list[str],
):
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    (tmp_path / "root" / "a").mkdir(parents=True)
    (tmp_path / "root" / "b").mkdir()
    (tmp_path / "root" / "notes.txt").write_text("x", encoding="utf-8")
    answer(
        card_app,
        monkeypatch,
        SessionFolder(SessionFolderKind.NO_LINK, "Alpha", root),
    )

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")

        await pilot.press("t")
        await pilot.pause()

        assert isinstance(card_app.screen, ModalSessionFolderScreen)
        assert card_app.screen.suggestions == expected


@pytest.mark.parametrize(
    ("ending", "typed"),
    [("submit", "~/x"), ("submit", "x"), ("escape", "~/x")],
    ids=["home-path", "relative-path", "escape"],
)
async def test_answering_the_folder_question_launches_there_and_escape_does_not(
    card_app: KanbanTui, monkeypatch, launches, tmp_path: Path, ending: str, typed: str
):
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x").mkdir()
    answer(
        card_app,
        monkeypatch,
        SessionFolder(SessionFolderKind.NO_LINK, "Alpha", "~/Projects"),
    )

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")
        await pilot.press("t")
        await pilot.pause()

        card_app.screen.query_one(Input).value = typed
        await pilot.press("enter" if ending == "submit" else "escape")
        await pilot.pause()

        assert not isinstance(card_app.screen, ModalSessionFolderScreen)
        expected = [(tmp_path / "x", "tackle-me", NOTE)] if ending == "submit" else []
        assert launches == expected


@pytest.mark.parametrize(
    "typed", ["missing", "file", "empty", "unknown-user", "markup"]
)
async def test_the_folder_question_refuses_what_is_not_a_folder(
    card_app: KanbanTui, monkeypatch, launches, tmp_path: Path, typed: str
):
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    value = {
        "missing": (tmp_path / "missing").as_posix(),
        "file": (tmp_path / "file.txt").as_posix(),
        "empty": "",
        "unknown-user": "~no-such-user-xyz/frontend",
        "markup": (tmp_path / "[/bold]").as_posix(),
    }[typed]
    answer(
        card_app,
        monkeypatch,
        SessionFolder(SessionFolderKind.NO_LINK, "Alpha", "~/Projects"),
    )

    async with card_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(card_app, pilot, "tackle-me")
        await pilot.press("t")
        await pilot.pause()
        hint = modal_text(card_app)

        card_app.screen.query_one(Input).value = value
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(card_app.screen, ModalSessionFolderScreen)
        assert card_app.screen.query_one(Input).value == value
        assert modal_text(card_app) != hint
        assert "not a folder" in modal_text(card_app)
        assert launches == []


async def test_t_starts_kitty_in_the_real_checkout_of_a_linked_project(
    vault_app: KanbanTui, test_vault: Path, tmp_path: Path, monkeypatch
):
    root = tmp_path / "root"
    checkout = make_checkout(root / "frontend", {"origin": f"git@{REMOTE}.git"})
    make_checkout(root / "other", {"origin": "https://github.com/someone/else"})
    (test_vault / "01-Projects/Alpha/_index.md").parent.mkdir(
        parents=True, exist_ok=True
    )
    (test_vault / "01-Projects/Alpha/_index.md").write_text(
        f"---\ntype: project\nrepos:\n  - {REMOTE}\n---\n", encoding="utf-8"
    )
    write_task_note(test_vault, NOTE, {"status": "pending", "board": "ready"})
    vault_app.config.backend.vault_settings.checkouts_root = root.as_posix()
    vault_app.backend = vault_app.get_backend()

    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("KITTY_LISTEN_ON", "unix:/tmp/kitty-1")
    monkeypatch.setattr(shutil, "which", lambda name: f"/opt/bin/{name}")
    kitty_calls: list[list[str]] = []
    real_run = subprocess.run

    def run(argv: list[str], **kwargs: Any) -> Any:
        if argv[0] == "/opt/bin/kitty":
            kitty_calls.append(argv)
            return SimpleNamespace(returncode=0, stderr="")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "tackle-me")

        await pilot.press("t")
        await pilot.pause()

        [argv] = kitty_calls
        assert argv[argv.index("--cwd") + 1] == checkout.as_posix()
        assert argv[-1] == f"/vault-pkm:tackle-task {NOTE}"
        assert errors(vault_app) == []
