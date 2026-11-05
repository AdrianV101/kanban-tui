import json
from datetime import date
from pathlib import Path

import pytest

from kanban_tui.backends.vault.backend import VaultBackend, VaultWriteError
from kanban_tui.backends.vault.jobs import sweep as sweep_module
from kanban_tui.backends.vault.jobs.capture import CAPTURE_PATH, CaptureWriteError
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
    assert agent.requests[0].since["granola"] == date(2026, 10, 28)
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


def test_draft_for_already_recorded_meeting_is_dropped(
    backend: VaultBackend, state_path: Path
):
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"meetings": {"granola:old": "2026-11-03"}}))
    outcome = result([draft("granola:old", "Already handled")], granola=["old"])
    report = sweep(backend, state_path, FakeAgent(outcome))
    assert report.created == []
    assert load_state(state_path).meetings == {"granola:old": "2026-11-03"}


def test_second_draft_for_same_capture_is_ignored(
    vault: Path, backend: VaultBackend, state_path: Path
):
    write_capture(vault, "- one\n")
    outcome = result([draft("capture:c1", "First"), draft("capture:c1", "Second")])
    report = sweep(backend, state_path, FakeAgent(outcome))
    assert report.ok and titles(backend).count("Second") == 0


@pytest.fixture
def read_only_alpha(vault: Path):
    folder = vault / "01-Projects/Alpha/tasks"
    folder.chmod(0o555)
    yield
    folder.chmod(0o755)


def test_write_failure_keeps_line_leaves_meeting_unmarked_and_files_card(
    vault: Path, backend: VaultBackend, state_path: Path, read_only_alpha
):
    capture = write_capture(vault, "- fix the bug\n")
    outcome = result(
        [
            draft("capture:c1", "Fix the bug", "Alpha"),
            draft("granola:m1", "Send quote", "Alpha"),
        ],
        granola=["m1"],
    )
    report = sweep(backend, state_path, FakeAgent(outcome))

    assert not report.ok
    assert capture.read_text() == "- fix the bug\n"
    assert "fix the bug" in report.errors[CAPTURE_CARD]
    assert "Send quote" in report.errors[GRANOLA_CARD]
    assert (vault / "00-Inbox/capture-sweep-capture-md-failed.md").exists()
    assert (vault / "00-Inbox/capture-sweep-granola-failed.md").exists()
    state = load_state(state_path)
    assert state.meetings == {}
    assert state.captures_written == {}
    assert state.last_success == {"plaud": ISO}


def test_card_creation_failure_is_reported_not_raised(
    vault: Path, backend: VaultBackend, state_path: Path
):
    (vault / "05-Templates/task.md").unlink()
    write_capture(vault, "- buy stamps\n")
    report = sweep(
        backend, state_path, FakeAgent(result([draft("capture:c1", "Buy stamps")]))
    )
    assert "buy stamps" in report.errors[CAPTURE_CARD]
    assert load_state(state_path).failure_cards == {}


@pytest.mark.parametrize(
    ("stage", "kept"), [("before agent", "2026-11-03"), ("after writes", ISO)]
)
def test_capture_removal_failure_keeps_entries_and_retries(
    vault: Path,
    backend: VaultBackend,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    kept: str,
):
    capture = write_capture(vault, "- buy stamps\n")
    if stage == "before agent":
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            json.dumps({"captures_written": {"- buy stamps": "2026-11-03"}})
        )
    failing = CaptureWriteError("Capture.md changed on every attempt")

    def refuse(vault_path, lines):
        raise failing

    monkeypatch.setattr(sweep_module, "remove_capture_lines", refuse)
    agent = FakeAgent(result([draft("capture:c1", "Buy stamps")]))
    report = sweep(backend, state_path, agent)

    assert "changed on every attempt" in report.errors[CAPTURE_CARD]
    assert titles(backend).count(CAPTURE_CARD) == 1
    assert capture.read_text() == "- buy stamps\n"
    assert load_state(state_path).captures_written == {"- buy stamps": kept}

    monkeypatch.undo()
    second = FakeAgent(result())
    sweep(backend, state_path, second)
    assert second.requests[0].captures == []
    assert capture.read_text() == ""
    assert load_state(state_path).captures_written == {}


def test_several_errors_for_one_title_share_one_card(
    vault: Path, backend: VaultBackend, state_path: Path
):
    write_capture(vault, "- one\n- two\n")
    report = sweep(backend, state_path, FakeAgent(result()))
    assert report.errors[CAPTURE_CARD] == (
        'no draft was written for "one"; no draft was written for "two"'
    )
    assert titles(backend).count(CAPTURE_CARD) == 1


def test_partial_meeting_failure_stays_marked_and_rerun_does_not_duplicate(
    vault: Path, backend: VaultBackend, state_path: Path, monkeypatch
):
    drafts = [
        draft("granola:m1", "First action"),
        draft("granola:m1", "Second action"),
    ]
    real = backend.create_new_task

    def fail_second(title, *args, **kwargs):
        if title == "Second action":
            raise VaultWriteError("disk full")
        return real(title, *args, **kwargs)

    monkeypatch.setattr(backend, "create_new_task", fail_second)
    report = sweep(backend, state_path, FakeAgent(result(drafts, granola=["m1"])))
    monkeypatch.undo()

    assert "Second action" in report.errors[GRANOLA_CARD]
    assert "granola:m1" in report.errors[GRANOLA_CARD]
    assert load_state(state_path).meetings == {"granola:m1": ISO}

    rerun = sweep(backend, state_path, FakeAgent(result(drafts, granola=["m1"])))
    assert rerun.created == []
    assert titles(backend).count("First action") == 1


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


def test_unexpected_agent_exception_files_the_general_card(
    vault: Path, backend: VaultBackend, state_path: Path
):
    capture = write_capture(vault, "- buy stamps\n")
    report = sweep(backend, state_path, FakeAgent(RuntimeError("boom\nbang")))

    assert not report.ok
    assert report.errors == {GENERAL: "RuntimeError: boom bang"}
    assert titles(backend).count(GENERAL) == 1
    assert capture.read_text() == "- buy stamps\n"
    assert load_state(state_path).failure_cards == {GENERAL: ISO}


def test_non_utf8_capture_files_the_general_card(
    vault: Path, backend: VaultBackend, state_path: Path
):
    path = vault / CAPTURE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"- caf\xe9\n")
    agent = FakeAgent(result())
    report = sweep(backend, state_path, agent)

    assert not report.ok
    assert GENERAL in report.errors
    assert report.errors[GENERAL].startswith("UnicodeDecodeError")
    assert titles(backend).count(GENERAL) == 1
    assert agent.requests == []


def test_model_text_cannot_run_templates_or_break_the_heading(
    vault: Path, backend: VaultBackend, state_path: Path
):
    write_capture(vault, "- buy stamps\n")
    hostile = Draft(
        "capture:c1",
        "Send\n<%* x %> quote\r\n\t now ",
        "Personal",
        "see <% tp.file.title %>",
        "",
    )
    meeting = Draft(
        "granola:m1", "Call <%* y %>", "Personal", "c", "https://x.test/<%a%>"
    )
    report = sweep(
        backend, state_path, FakeAgent(result([hostile, meeting], granola=["m1"]))
    )

    assert report.ok
    assert len(report.created) == 2
    for rel in report.created:
        text = (vault / rel).read_text(encoding="utf-8")
        assert "<%" not in text
        headings = [line for line in text.splitlines() if line.startswith("# ")]
        assert len(headings) == 1
    first = (vault / report.created[0]).read_text(encoding="utf-8")
    assert "# Send < %* x %> quote now" in first
