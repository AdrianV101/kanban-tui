from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from kanban_tui.backends.vault.open_note import open_note

URL = "obsidian://open?vault=V&file=00-Inbox%2Fnote"


class FakeApp:
    def __init__(self, is_web: bool = False) -> None:
        self.is_web = is_web
        self.opened: list[str] = []
        self.notices: list[tuple[str, str]] = []

    def open_url(self, url: str) -> None:
        self.opened.append(url)

    def notify(self, message: str, *, severity: str = "information") -> None:
        self.notices.append((message, severity))


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_macos_terminal_hands_the_url_to_the_system(
    monkeypatch: pytest.MonkeyPatch, commands: list[list[str]]
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    app = FakeApp()

    open_note(app, URL)

    assert commands == [["/usr/bin/open", URL]]
    assert app.opened == []
    assert app.notices == []


@pytest.mark.parametrize(
    ("platform", "is_web"),
    [("darwin", True), ("linux", False), ("linux", True)],
)
def test_other_hosts_use_the_app(
    monkeypatch: pytest.MonkeyPatch,
    commands: list[list[str]],
    platform: str,
    is_web: bool,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    app = FakeApp(is_web=is_web)

    open_note(app, URL)

    assert commands == []
    assert app.opened == [URL]


def test_failure_to_open_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **_: SimpleNamespace(returncode=1, stderr="no application\n"),
    )
    app = FakeApp()

    open_note(app, URL)

    assert app.notices == [("Could not open the note: no application", "error")]
