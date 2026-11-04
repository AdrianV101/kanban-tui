from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from kanban_tui.backends.vault.backend import VaultBackend, VaultWriteError
from kanban_tui.backends.vault.jobs.capture import (
    CaptureItem,
    CaptureWriteError,
    read_capture_items,
    remove_capture_lines,
)
from kanban_tui.backends.vault.jobs.sweep_agent import (
    SOURCES,
    AgentError,
    AgentResult,
    Draft,
    SweepRequest,
)
from kanban_tui.backends.vault.jobs.sweep_state import (
    StateError,
    SweepState,
    load_state,
    prune,
    save_state,
)
from kanban_tui.classes.task import Task

PROPOSED_COLUMN = 1
GENERAL_TITLE = "Capture sweep failed"
CAPTURE_TITLE = "Capture sweep: Capture.md failed"
CAPTURE_PREFIX = "capture:"


@dataclass
class SweepReport:
    created: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _source_title(source: str) -> str:
    return f"Capture sweep: {source.capitalize()} failed"


def run_sweep(
    backend: VaultBackend,
    state_path: Path,
    agent: Callable[[SweepRequest], AgentResult],
    owner_name: str,
    today: date,
) -> SweepReport:
    """Turn captures and meeting action items into Proposed task notes.

    Every failure becomes a card on the board. Vault and capture errors never
    raise out; they land in the report.
    """
    report = SweepReport()
    problems: dict[str, list[str]] = {}
    state: SweepState | None = None

    def problem(title: str, message: str) -> None:
        problems.setdefault(title, []).append(message)

    try:
        state = load_state(state_path)
    except StateError as error:
        problem(GENERAL_TITLE, str(error))
        _file_cards(backend, report, problems, None, today)
        return report

    vault = Path(backend.settings.vault_path).expanduser()
    try:
        _sweep(
            backend, vault, state, state_path, agent, owner_name, today, report, problem
        )
    finally:
        _file_cards(backend, report, problems, state, today)
        prune(state, today)
        save_state(state_path, state)
    return report


def _sweep(
    backend: VaultBackend,
    vault: Path,
    state: SweepState,
    state_path: Path,
    agent: Callable[[SweepRequest], AgentResult],
    owner_name: str,
    today: date,
    report: SweepReport,
    problem: Callable[[str, str], None],
) -> None:
    if state.captures_written:
        _remove_written(vault, state, list(state.captures_written), problem)

    items = [
        item
        for item in read_capture_items(vault)
        if item.line not in state.captures_written
    ]
    projects = backend.writable_projects()
    request = SweepRequest(
        today=today,
        owner_name=owner_name,
        projects=list(projects),
        captures=items,
        since={source: _since(state, source, today) for source in SOURCES},
        processed=sorted(state.meetings),
    )
    try:
        result = agent(request)
    except AgentError as error:
        problem(GENERAL_TITLE, str(error))
        return

    for source in SOURCES:
        if result.errors.get(source):
            problem(_source_title(source), str(result.errors[source]))
    failed_sources = {s for s in SOURCES if result.errors.get(s)}

    by_capture, by_meeting = _validate(result, items, state)
    categories = {name.lower(): number for name, number in projects.items()}
    iso_today = today.isoformat()

    failed_meetings: set[str] = set()
    written_lines: list[str] = []
    for item_id, draft in by_capture.items():
        item = next(i for i in items if i.id == item_id)
        note = _write(backend, draft, categories, f"Capture.md {iso_today}")
        if isinstance(note, str):
            problem(CAPTURE_TITLE, f'could not write "{item.text}": {note}')
            continue
        report.created.append(note.metadata["note_path"])
        written_lines.append(item.line)
        state.captures_written[item.line] = iso_today
        save_state(state_path, state)
    for key, drafts in by_meeting.items():
        for draft in drafts:
            note = _write(backend, draft, categories, _meeting_source(draft))
            if isinstance(note, str):
                failed_meetings.add(key)
                failed_sources.add(key.split(":", 1)[0])
                problem(_source_title(key.split(":", 1)[0]), f"{draft.title}: {note}")
                continue
            report.created.append(note.metadata["note_path"])
            save_state(state_path, state)

    for item in items:
        if item.id not in by_capture:
            problem(CAPTURE_TITLE, f'no draft was written for "{item.text}"')

    for source in SOURCES:
        for meeting_id in result.examined.get(source, []):
            key = f"{source}:{meeting_id}"
            if key not in state.meetings and key not in failed_meetings:
                state.meetings[key] = iso_today

    if written_lines:
        _remove_written(vault, state, written_lines, problem)

    for source in SOURCES:
        if source not in failed_sources:
            state.last_success[source] = iso_today


def _remove_written(
    vault: Path,
    state: SweepState,
    lines: list[str],
    problem: Callable[[str, str], None],
) -> None:
    try:
        remove_capture_lines(vault, lines)
    except CaptureWriteError as error:
        problem(CAPTURE_TITLE, str(error))
        return
    for line in lines:
        state.captures_written.pop(line, None)


def _since(state: SweepState, source: str, today: date) -> date:
    try:
        return date.fromisoformat(state.last_success[source]) - timedelta(days=1)
    except (KeyError, ValueError):
        return today - timedelta(days=2)


def _validate(
    result: AgentResult, items: list[CaptureItem], state: SweepState
) -> tuple[dict[str, Draft], dict[str, list[Draft]]]:
    sent = {item.id for item in items}
    by_capture: dict[str, Draft] = {}
    by_meeting: dict[str, list[Draft]] = {}
    for draft in result.drafts:
        key = draft.source_key
        if key.startswith(CAPTURE_PREFIX):
            item_id = key.removeprefix(CAPTURE_PREFIX)
            if item_id in sent and item_id not in by_capture:
                by_capture[item_id] = draft
            continue
        source, _, meeting_id = key.partition(":")
        if (
            source in SOURCES
            and meeting_id in result.examined.get(source, [])
            and key not in state.meetings
        ):
            by_meeting.setdefault(key, []).append(draft)
    return by_capture, by_meeting


def _meeting_source(draft: Draft) -> str:
    return draft.link if draft.link.startswith("https://") else draft.source_key


def _write(
    backend: VaultBackend,
    draft: Draft,
    categories: dict[str, int | None],
    source: str,
) -> Task | str:
    category = categories.get(draft.project.strip().lower())
    try:
        return backend.create_new_task(
            title=draft.title,
            description=draft.context,
            column=PROPOSED_COLUMN,
            category=category,
            source=source,
        )
    except VaultWriteError as error:
        return str(error)


def _file_cards(
    backend: VaultBackend,
    report: SweepReport,
    problems: dict[str, list[str]],
    state: SweepState | None,
    today: date,
) -> None:
    iso_today = today.isoformat()
    for title, messages in problems.items():
        error = "; ".join(messages)
        report.errors[title] = error
        if state is not None and state.failure_cards.get(title) == iso_today:
            continue
        try:
            backend.create_new_task(
                title=title,
                description=f"{error}\n\nThe sweep tries again on its next run.",
                column=PROPOSED_COLUMN,
                category=None,
            )
        except VaultWriteError:
            continue
        if state is not None:
            state.failure_cards[title] = iso_today
