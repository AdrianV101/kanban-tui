from datetime import date, datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from kanban_tui.backends.vault.backend import VaultBackend, VaultWriteError
from kanban_tui.backends.vault.notes import note_filename, read_task_note
from kanban_tui.config import VaultBackendSettings
from tests.conftest import write_task_note

FROZEN_DAY = "2026-11-04"
WORK_TASKS = "01-Projects/Work/tasks"
SIDE_PROJECT_TASKS = "01-Projects/Side Project/tasks"


def make_backend(vault: Path) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix()))


def seed_vault(vault: Path, personal: bool = True) -> VaultBackend:
    write_task_note(vault, f"{WORK_TASKS}/seed.md", {"project": "Work"})
    write_task_note(vault, f"{SIDE_PROJECT_TASKS}/seed.md", {"project": "Side Project"})
    if personal:
        write_task_note(vault, "00-Inbox/seed.md")
    return make_backend(vault)


def category_id(backend: VaultBackend, name: str) -> int:
    backend.get_tasks_on_active_board()
    return next(c.category_id for c in backend.get_all_categories() if c.name == name)


def list_files(vault: Path) -> set[Path]:
    return {path for path in vault.rglob("*") if path.is_file()}


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "column,status,board",
    [(1, "pending", "proposed"), (2, "pending", "ready"), (3, "active", "doing")],
)
def test_a_new_card_carries_its_columns_fields(
    test_vault: Path, column: int, status: str, board: str
):
    backend = seed_vault(test_vault)

    task = backend.create_new_task("Fresh", "", column=column)

    note = read_task_note(test_vault / "00-Inbox/fresh.md", test_vault)
    assert note is not None
    assert (note.status, note.board) == (status, board)
    assert note.status in {"pending", "active", "done", "cancelled"}
    assert task.column == column
    assert task.metadata["board"] == board


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "category_name,personal_notes,folder,project,due_input",
    [
        ("Work", True, WORK_TASKS, "Work", datetime(2026, 12, 1)),
        (
            "Side Project",
            True,
            SIDE_PROJECT_TASKS,
            "Side Project",
            "2026-12-01 00:00:00",
        ),
        ("Personal", True, "00-Inbox", None, None),
        (None, False, "00-Inbox", None, "2026-12-01 00:00:00"),
    ],
)
def test_a_new_card_becomes_a_full_task_note(
    test_vault: Path,
    category_name: str | None,
    personal_notes: bool,
    folder: str,
    project: str | None,
    due_input: datetime | str | None,
):
    backend = seed_vault(test_vault, personal=personal_notes)
    category = category_id(backend, category_name) if category_name else None

    task = backend.create_new_task(
        title="Write the report",
        description="First line\n\nSecond paragraph",
        column=3,
        category=category,
        due_date=due_input,
    )

    path = test_vault / folder / "write-the-report.md"
    note = read_task_note(path, test_vault)
    assert note is not None
    assert note.title == "Write the report"
    assert note.project == project
    assert note.created == date(2026, 11, 4)
    assert note.due == (date(2026, 12, 1) if due_input else None)
    assert note.description == "First line\n\nSecond paragraph"
    text = path.read_text()
    assert "<%" not in text
    assert "## Context" in text and "## Acceptance Criteria" in text
    assert task.column == 3
    assert task.title == "Write the report"
    assert task.metadata["note_path"] == f"{folder}/write-the-report.md"
    assert task in backend.get_tasks_on_active_board()


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Fix: flaky/CI test", "fix-flaky-ci-test.md"),
        ("  Plain   title  ", "plain-title.md"),
        ("Ship it 🚀🔥", "ship-it.md"),
        ("🔥", "task.md"),
        ("?!...", "task.md"),
    ],
)
def test_filenames_are_kebab_case(title: str, expected: str):
    assert note_filename(title) == expected


def test_a_clashing_filename_gets_a_numbered_suffix_and_is_never_overwritten(
    test_vault: Path,
):
    backend = seed_vault(test_vault)
    work = category_id(backend, "Work")
    existing = test_vault / WORK_TASKS / "fix-it.md"
    existing.write_text("my own note", encoding="utf-8")

    for _ in range(3):
        backend.create_new_task("Fix it", "", column=2, category=work)

    assert existing.read_text() == "my own note"
    created = {p.name for p in (test_vault / WORK_TASKS).glob("fix-it*.md")}
    assert created == {"fix-it.md", "fix-it-2.md", "fix-it-3.md", "fix-it-4.md"}


@pytest.mark.parametrize("problem", ["missing_template", "unknown_category"])
def test_creation_is_refused_when_it_cannot_be_done_correctly(
    test_vault: Path, problem: str
):
    backend = seed_vault(test_vault)
    work = category_id(backend, "Work")
    if problem == "missing_template":
        (test_vault / "05-Templates/task.md").unlink()
    before = list_files(test_vault)

    with pytest.raises(VaultWriteError):
        backend.create_new_task(
            "Anything",
            "",
            column=2,
            category=work if problem == "missing_template" else 999,
        )

    assert list_files(test_vault) == before
