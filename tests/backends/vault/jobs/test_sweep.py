import json
from datetime import date
from pathlib import Path

import pytest

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.jobs.capture import CAPTURE_PATH
from kanban_tui.backends.vault.jobs.sweep import run_sweep
from kanban_tui.backends.vault.jobs.sweep_agent import (
    AgentError,
    AgentResult,
    Draft,
    SweepRequest,
)
from kanban_tui.backends.vault.jobs.sweep_state import load_state
from kanban_tui.config import VaultBackendSettings
from tests.conftest import write_task_note

TODAY = date(2026, 11, 4)
ISO = TODAY.isoformat()
GENERAL = "Capture sweep failed"
CAPTURE_CARD = "Capture sweep: Capture.md failed"
GRANOLA_CARD = "Capture sweep: Granola failed"


class FakeAgent:
    def __init__(self, result: AgentResult | Exception):
        self.result = result
        self.requests: list[SweepRequest] = []

    def __call__(self, request: SweepRequest) -> AgentResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def result(drafts=(), granola=(), plaud=(), errors=None) -> AgentResult:
    return AgentResult(
        drafts=list(drafts),
        examined={"granola": list(granola), "plaud": list(plaud)},
        errors={"granola": None, "plaud": None} | (errors or {}),
    )


def draft(key: str, title: str, project: str = "Personal", link: str = "") -> Draft:
    return Draft(key, title, project, f"context for {title}", link)


@pytest.fixture
def vault(test_vault: Path) -> Path:
    write_task_note(test_vault, "01-Projects/Alpha/tasks/seed.md", {"status": "active"})
    return test_vault


@pytest.fixture
def backend(vault: Path) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix()))


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "sweep.json"


def write_capture(vault: Path, content: str) -> Path:
    path = vault / CAPTURE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def sweep(backend, state_path, agent):
    return run_sweep(backend, state_path, agent, "Alex", TODAY)


def titles(backend: VaultBackend) -> list[str]:
    return sorted(t.title for t in backend.get_tasks_on_active_board())


def test_happy_path_writes_proposed_notes_and_records_state(
    vault: Path, backend: VaultBackend, state_path: Path
):
    capture = write_capture(vault, "- buy stamps\n- fix the Alpha bug\n- odd one\n")
    agent = FakeAgent(
        result(
            [
                draft("capture:c1", "Buy stamps"),
                draft("capture:c2", "Fix the bug", "alpha"),
                draft("capture:c3", "Odd thing", "Nowhere"),
                draft(
                    "granola:m1",
                    "Send the quote",
                    "Alpha",
                    "https://notes.example/m1",
                ),
                draft("plaud:p1", "Call back", "Personal", "not a link"),
            ],
            granola=["m1", "m2"],
            plaud=["p1"],
        )
    )
    report = sweep(backend, state_path, agent)

    assert report.ok and report.errors == {}
    assert sorted(report.created) == sorted(
        [
            "00-Inbox/buy-stamps.md",
            "01-Projects/Alpha/tasks/fix-the-bug.md",
            "00-Inbox/odd-thing.md",
            "01-Projects/Alpha/tasks/send-the-quote.md",
            "00-Inbox/call-back.md",
        ]
    )
    quote = (vault / "01-Projects/Alpha/tasks/send-the-quote.md").read_text()
    assert "context for Send the quote" in quote
    assert 'source: "https://notes.example/m1"' in quote
    assert f"source: Capture.md {ISO}" in (vault / "00-Inbox/buy-stamps.md").read_text()
    assert 'source: "plaud:p1"' in (vault / "00-Inbox/call-back.md").read_text()
    assert capture.read_text() == ""
    state = load_state(state_path)
    assert set(state.meetings) == {"granola:m1", "granola:m2", "plaud:p1"}
    assert state.captures_written == {}
    assert state.last_success == {"granola": ISO, "plaud": ISO}
    assert agent.requests[0].projects == ["Alpha", "Personal"]
    assert agent.requests[0].since["granola"] == date(2026, 11, 2)


def test_rerun_creates_nothing_and_sends_processed_meetings(
    vault: Path, backend: VaultBackend, state_path: Path
):
    drafts = [draft("granola:m1", "Send the quote")]
    sweep(backend, state_path, FakeAgent(result(drafts, granola=["m1"])))
    agent = FakeAgent(result(drafts, granola=["m1"]))
    report = sweep(backend, state_path, agent)

    assert report.created == [] and report.ok
    assert agent.requests[0].processed == ["granola:m1"]
    assert agent.requests[0].since["granola"] == date(2026, 11, 3)
    assert titles(backend).count("Send the quote") == 1


def test_crash_recovery_removes_written_line_without_resending(
    vault: Path, backend: VaultBackend, state_path: Path
):
    capture = write_capture(vault, "- done already\n- new one\n")
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"captures_written": {"- done already": "2026-11-03"}})
    )
    agent = FakeAgent(result([draft("capture:c1", "New thing")]))
    report = sweep(backend, state_path, agent)

    assert [c.text for c in agent.requests[0].captures] == ["new one"]
    assert report.ok
    assert capture.read_text() == ""
    assert load_state(state_path).captures_written == {}


def test_source_error_makes_one_card_and_holds_back_that_source(
    vault: Path, backend: VaultBackend, state_path: Path
):
    write_capture(vault, "- buy stamps\n")
    outcome = result(
        [draft("capture:c1", "Buy stamps"), draft("granola:m1", "Partial")],
        granola=["m1"],
        errors={"granola": "token expired"},
    )
    report = sweep(backend, state_path, FakeAgent(outcome))

    assert not report.ok
    assert report.errors == {GRANOLA_CARD: "token expired"}
    assert "Buy stamps" in titles(backend) and "Partial" in titles(backend)
    state = load_state(state_path)
    assert state.last_success == {"plaud": ISO}
    assert state.failure_cards == {GRANOLA_CARD: ISO}

    second = sweep(backend, state_path, FakeAgent(result(errors={"granola": "x"})))
    assert second.errors == {GRANOLA_CARD: "x"}
    assert titles(backend).count(GRANOLA_CARD) == 1


def test_agent_error_makes_one_card_and_touches_nothing_else(
    vault: Path, backend: VaultBackend, state_path: Path
):
    capture = write_capture(vault, "- buy stamps\r\n- second\n")
    before = capture.read_bytes()
    report = sweep(backend, state_path, FakeAgent(AgentError("claude exploded")))

    assert not report.ok
    assert report.errors == {GENERAL: "claude exploded"}
    assert titles(backend).count(GENERAL) == 1
    assert capture.read_bytes() == before
    state = load_state(state_path)
    assert state.meetings == {} and state.captures_written == {}
    assert state.last_success == {}
    assert state.failure_cards == {GENERAL: ISO}


@pytest.mark.parametrize(
    "drafts",
    [
        [],
        [draft("capture:c9", "Unknown capture")],
        [draft("granola:other", "Not examined"), draft("bogus", "No source")],
    ],
)
def test_invalid_output_is_dropped_and_unwritten_capture_stays(
    vault: Path, backend: VaultBackend, state_path: Path, drafts
):
    capture = write_capture(vault, "- remember the milk\n")
    report = sweep(backend, state_path, FakeAgent(result(drafts, granola=["m1"])))

    assert report.created == []
    assert capture.read_text() == "- remember the milk\n"
    assert "remember the milk" in report.errors[CAPTURE_CARD]
    assert load_state(state_path).meetings == {"granola:m1": ISO}


def test_second_draft_for_same_capture_is_ignored(
    vault: Path, backend: VaultBackend, state_path: Path
):
    write_capture(vault, "- one\n")
    outcome = result([draft("capture:c1", "First"), draft("capture:c1", "Second")])
    report = sweep(backend, state_path, FakeAgent(outcome))
    assert report.ok and titles(backend).count("Second") == 0


def test_write_failure_keeps_line_and_leaves_meeting_unmarked(
    vault: Path, backend: VaultBackend, state_path: Path
):
    (vault / "05-Templates/task.md").unlink()
    capture = write_capture(vault, "- buy stamps\n")
    outcome = result(
        [draft("capture:c1", "Buy stamps"), draft("granola:m1", "Send quote")],
        granola=["m1"],
    )
    report = sweep(backend, state_path, FakeAgent(outcome))

    assert not report.ok
    assert capture.read_text() == "- buy stamps\n"
    assert "buy stamps" in report.errors[CAPTURE_CARD]
    assert GRANOLA_CARD in report.errors
    state = load_state(state_path)
    assert state.meetings == {}
    assert state.last_success == {"plaud": ISO}


def test_unreadable_state_makes_one_card_and_changes_nothing(
    vault: Path, backend: VaultBackend, state_path: Path
):
    capture = write_capture(vault, "- buy stamps\n")
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not json")
    agent = FakeAgent(result())
    report = sweep(backend, state_path, agent)

    assert list(report.errors) == [GENERAL]
    assert agent.requests == []
    assert state_path.read_text() == "{not json"
    assert capture.read_text() == "- buy stamps\n"
    assert titles(backend).count(GENERAL) == 1
