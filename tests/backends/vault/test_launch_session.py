from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kanban_tui.backends.vault.launch_session import launch_session

KITTY = "/opt/bin/kitty"
CLAUDE = "/opt/bin/claude"
TITLE = 'Fix "quotes" in Größe'
NOTE = "01-Projects/My Project/tasks/a b.md"
SETUP_LINES = ("allow_remote_control socket-only", "listen_on unix:/tmp/kitty")


class FakeApp:
    def __init__(self) -> None:
        self.is_web = False
        self.opened: list[str] = []
        self.notices: list[tuple[str, str]] = []

    def open_url(self, url: str) -> None:
        self.opened.append(url)

    def notify(self, message: str, *, severity: str = "information") -> None:
        self.notices.append((message, severity))


@pytest.fixture
def kitty_result() -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stderr="")


@pytest.fixture
def commands(
    monkeypatch: pytest.MonkeyPatch, kitty_result: SimpleNamespace
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> SimpleNamespace:
        calls.append(argv)
        return kitty_result

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


@pytest.fixture
def programs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str | None]:
    found: dict[str, str | None] = {"kitty": KITTY, "claude": CLAUDE}
    monkeypatch.setattr(shutil, "which", lambda name: found.get(name))
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("KITTY_LISTEN_ON", "unix:/tmp/kitty-123")
    return found


def test_inside_kitty_the_tab_runs_tackle_task_in_the_folder(
    tmp_path: Path, commands: list[list[str]], programs: dict[str, str | None]
):
    app = FakeApp()

    started = launch_session(app, tmp_path, TITLE, NOTE)

    assert started is True
    assert commands == [
        [
            KITTY,
            "@",
            "launch",
            "--type=tab",
            "--keep-focus",
            "--copy-env",
            "--tab-title",
            TITLE,
            "--cwd",
            tmp_path.as_posix(),
            CLAUDE,
            f"/vault-pkm:tackle-task {NOTE}",
        ]
    ]
    assert app.notices == []


@pytest.mark.parametrize("missing", ["KITTY_WINDOW_ID", "KITTY_LISTEN_ON"])
def test_without_kitty_remote_control_nothing_starts_and_the_setup_is_shown(
    tmp_path: Path,
    commands: list[list[str]],
    programs: dict[str, str | None],
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
):
    monkeypatch.delenv(missing)
    app = FakeApp()

    started = launch_session(app, tmp_path, TITLE, NOTE)

    assert started is False
    assert commands == []
    [(message, severity)] = app.notices
    assert severity == "error"
    assert all(line in message for line in SETUP_LINES)


def test_a_refused_launch_shows_kitty_s_error(
    tmp_path: Path,
    commands: list[list[str]],
    programs: dict[str, str | None],
    kitty_result: SimpleNamespace,
):
    kitty_result.returncode = 1
    kitty_result.stderr = "Error: Remote control is disabled\n"
    app = FakeApp()

    started = launch_session(app, tmp_path, TITLE, NOTE)

    assert started is False
    [(message, severity)] = app.notices
    assert severity == "error"
    assert "Remote control is disabled" in message


@pytest.mark.parametrize(
    ("program", "named"), [("claude", "Claude Code"), ("kitty", "kitty")]
)
def test_a_missing_program_starts_nothing_and_says_which(
    tmp_path: Path,
    commands: list[list[str]],
    programs: dict[str, str | None],
    monkeypatch: pytest.MonkeyPatch,
    program: str,
    named: str,
):
    programs[program] = None
    monkeypatch.setattr(
        "kanban_tui.backends.vault.launch_session.KITTY_APP_BINARY",
        tmp_path / "no-kitty",
    )
    app = FakeApp()

    started = launch_session(app, tmp_path, TITLE, NOTE)

    assert started is False
    assert commands == []
    [(message, severity)] = app.notices
    assert severity == "error"
    assert f"{named} was not found" in message
