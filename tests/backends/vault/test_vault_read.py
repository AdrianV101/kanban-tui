import os
from datetime import date, datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from kanban_tui.backends.vault.backend import COLUMN_NAMES, VaultBackend
from kanban_tui.config import VaultBackendSettings
from tests.conftest import write_task_note


def make_backend(vault: Path, **settings) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix(), **settings))


def titles(backend: VaultBackend) -> set[str]:
    return {task.title for task in backend.get_tasks_on_active_board()}


def test_only_task_notes_under_the_globs_become_cards(test_vault: Path):
    write_task_note(test_vault, "01-Projects/X/tasks/in-project.md")
    write_task_note(test_vault, "00-Inbox/in-inbox.md")
    write_task_note(test_vault, "00-Inbox/audio-ingestion/ingested.md")
    write_task_note(test_vault, "04-Archive/archived.md")
    write_task_note(test_vault, "01-Projects/X/tasks/research.md", {"type": "research"})

    assert titles(make_backend(test_vault)) == {"in-project", "in-inbox"}


def test_vault_without_task_notes_gives_an_empty_board(test_vault: Path):
    (test_vault / "00-Inbox").mkdir()
    (test_vault / "00-Inbox/plain.md").write_text("just a note\n", encoding="utf-8")
    backend = make_backend(test_vault)

    assert backend.get_tasks_on_active_board() == []
    assert backend.get_warnings() == []


@pytest.mark.parametrize("problem", ["empty_path", "missing_dir", "no_glob_match"])
def test_a_vault_that_cannot_give_notes_is_named_in_a_warning(
    test_vault: Path, tmp_path: Path, problem: str
):
    if problem == "empty_path":
        backend = VaultBackend(VaultBackendSettings(vault_path=""))
    elif problem == "missing_dir":
        backend = make_backend(tmp_path / "typo")
    else:
        backend = make_backend(test_vault)

    assert backend.get_tasks_on_active_board() == []
    (warning,) = backend.get_warnings()
    expected = {
        "empty_path": "vault_path",
        "missing_dir": "typo",
        "no_glob_match": "01-Projects/*/tasks/*.md",
    }[problem]
    assert expected in warning


@pytest.mark.parametrize(
    "status,board,column",
    [
        ("pending", None, 1),
        ("pending", "proposed", 1),
        ("pending", "ready", 2),
        ("pending", "in-review", 1),
        ("pending", "junk", 1),
        ("active", None, 3),
        ("active", "doing", 3),
        ("active", "ready", 3),
        ("active", "in-review", 4),
        ("done", "ready", 5),
        ("done", None, 5),
        ("cancelled", "in-review", 6),
    ],
)
def test_status_and_board_map_to_a_column(
    test_vault: Path, status: str, board: str | None, column: int
):
    write_task_note(
        test_vault,
        "00-Inbox/note.md",
        {"status": status, "board": board, "finished": date.today().isoformat()},
    )

    (task,) = make_backend(test_vault).get_tasks_on_active_board()

    assert task.column == column
    assert "unknown_status" not in task.metadata


@pytest.mark.parametrize("board", [None, "ready"])
@pytest.mark.parametrize("status", [None, "approved", "superseded"])
def test_missing_or_unknown_status_shows_in_proposed(
    test_vault: Path, status: str | None, board: str | None
):
    write_task_note(test_vault, "00-Inbox/note.md", {"status": status, "board": board})

    (task,) = make_backend(test_vault).get_tasks_on_active_board()

    assert task.column == 1
    if status is None:
        assert task.metadata["unknown_status"] is None
    else:
        assert task.metadata["unknown_status"] == status


def test_scanned_status_board_and_column_are_recorded(test_vault: Path):
    write_task_note(
        test_vault, "00-Inbox/a.md", {"status": "active", "board": "in-review"}
    )
    write_task_note(test_vault, "00-Inbox/b.md", {"status": "pending"})

    by_title = {
        t.title: t for t in make_backend(test_vault).get_tasks_on_active_board()
    }

    a, b = by_title["a"].metadata, by_title["b"].metadata
    assert (a["status"], a["board"], a["column"]) == ("active", "in-review", 4)
    assert (b["status"], b["board"], b["column"]) == ("pending", None, 1)


def test_there_is_one_board_with_six_columns(test_vault: Path):
    backend = make_backend(test_vault)

    (board,) = backend.get_boards()
    columns = backend.get_columns()

    assert board.name == "Vault"
    assert backend.active_board == board
    assert [column.name for column in columns] == [
        "Proposed",
        "Ready",
        "Doing",
        "In Review",
        "Done",
        "Archive",
    ]
    assert [column.name for column in columns] == list(COLUMN_NAMES.values())
    assert [column.visible for column in columns] == [True] * 5 + [False]
    assert [column.column_id for column in columns] == [1, 2, 3, 4, 5, 6]
    assert (board.reset_column, board.start_column, board.finish_column) == (2, 3, 5)
    assert backend.get_column_by_id(3) == columns[2]
    assert backend.get_board_infos()[0]["name"] == "Vault"


def test_category_comes_from_project_then_folder_then_personal(test_vault: Path):
    write_task_note(test_vault, "01-Projects/Alpha/tasks/a.md", {"project": "Beta"})
    write_task_note(test_vault, "01-Projects/Alpha/tasks/b.md")
    write_task_note(test_vault, "00-Inbox/c.md")
    backend = make_backend(test_vault)

    by_title = {t.title: t for t in backend.get_tasks_on_active_board()}
    names = {c.category_id: c.name for c in backend.get_all_categories()}

    assert names[by_title["a"].category] == "Beta"
    assert names[by_title["b"].category] == "Alpha"
    assert names[by_title["c"].category] == "Personal"


def test_category_colour_comes_from_settings_or_a_fixed_palette(test_vault: Path):
    write_task_note(test_vault, "01-Projects/Alpha/tasks/a.md")
    write_task_note(test_vault, "01-Projects/Beta/tasks/b.md")
    write_task_note(test_vault, "01-Projects/Gamma/tasks/c.md")
    settings = {"project_colors": {"Beta": "#123456"}}

    first = make_backend(test_vault, **settings)
    first.get_tasks_on_active_board()
    second = make_backend(test_vault, **settings)
    second.get_tasks_on_active_board()

    colours = {c.name: c.color for c in first.get_all_categories()}
    assert colours["Beta"] == "#123456"
    assert colours["Alpha"] != colours["Gamma"]
    assert colours == {c.name: c.color for c in second.get_all_categories()}


def test_a_project_keeps_its_category_id_when_a_new_project_appears(test_vault: Path):
    write_task_note(test_vault, "01-Projects/Beta/tasks/b.md")
    backend = make_backend(test_vault)
    backend.get_tasks_on_active_board()
    beta = next(c for c in backend.get_all_categories() if c.name == "Beta")

    write_task_note(test_vault, "01-Projects/Alpha/tasks/a.md")
    tasks = backend.get_tasks_on_active_board()

    categories = {c.name: c for c in backend.get_all_categories()}
    assert categories["Beta"] == beta
    assert categories["Alpha"].category_id != beta.category_id
    assert backend.get_category_by_id(beta.category_id) == beta
    assert {t.category for t in tasks} == {c.category_id for c in categories.values()}


def test_card_fields_come_from_the_note(test_vault: Path):
    write_task_note(
        test_vault,
        "00-Inbox/with-heading.md",
        {"due": "2026-11-20", "created": "2026-10-01"},
        "# Real Title\n\n## Description\nFirst line\nSecond line\n\n## Context\nnot this\n",
    )
    write_task_note(test_vault, "00-Inbox/no-heading.md", {"created": "2026-10-02"})

    by_title = {
        t.title: t for t in make_backend(test_vault).get_tasks_on_active_board()
    }

    card = by_title["Real Title"]
    assert card.description == "First line\nSecond line"
    assert card.due_date == datetime(2026, 11, 20)
    assert card.creation_date == datetime(2026, 10, 1)
    assert card.metadata["note_path"] == "00-Inbox/with-heading.md"
    plain = by_title["no-heading"]
    assert plain.description == ""
    assert plain.due_date is None


def test_creation_date_falls_back_to_file_modification_time(test_vault: Path):
    path = write_task_note(test_vault, "00-Inbox/note.md")
    modified = datetime(2026, 9, 9, 8, 30).timestamp()
    os.utime(path, (modified, modified))

    (task,) = make_backend(test_vault).get_tasks_on_active_board()

    assert task.creation_date == datetime(2026, 9, 9, 8, 30)


@pytest.mark.parametrize("field", ["due", "created"])
def test_unparseable_date_gives_no_date_and_one_warning(test_vault: Path, field: str):
    write_task_note(test_vault, "00-Inbox/bad-date.md", {field: "next tuesday"})
    backend = make_backend(test_vault)

    (task,) = backend.get_tasks_on_active_board()

    if field == "due":
        assert task.due_date is None
    else:
        assert task.creation_date is not None
    warnings = backend.get_warnings()
    assert len(warnings) == 1
    assert "00-Inbox/bad-date.md" in warnings[0]


def test_cards_are_ordered_by_priority_then_due_then_created(test_vault: Path):
    def note(name: str, **fields):
        write_task_note(test_vault, f"00-Inbox/{name}.md", fields)

    note("none-priority", created="2026-01-01")
    note("low", priority="low", created="2026-01-01")
    note("normal-late", priority="normal", due="2026-12-01", created="2026-01-01")
    note("normal-early", priority="normal", due="2026-11-01", created="2026-02-01")
    note("normal-no-due-old", priority="normal", created="2026-01-01")
    note("normal-no-due-new", priority="normal", created="2026-03-01")
    note("high", priority="high", created="2026-01-01")
    note("urgent", priority="urgent", created="2026-01-01")

    tasks = make_backend(test_vault).get_tasks_on_active_board()
    ordered = sorted(tasks, key=lambda t: t.position)

    assert [t.title for t in ordered] == [
        "urgent",
        "high",
        "normal-early",
        "normal-late",
        "normal-no-due-old",
        "normal-no-due-new",
        "low",
        "none-priority",
    ]
    assert [t.position for t in ordered] == list(range(8))


def test_positions_restart_in_each_column(test_vault: Path):
    write_task_note(test_vault, "00-Inbox/a.md", {"status": "pending"})
    write_task_note(test_vault, "00-Inbox/b.md", {"status": "active"})

    tasks = make_backend(test_vault).get_tasks_on_active_board()

    assert [t.position for t in tasks] == [0, 0]


@freeze_time("2026-11-04 12:00:00")
def test_done_notes_show_only_within_the_visible_window(test_vault: Path):
    done = {"status": "done"}
    write_task_note(
        test_vault, "00-Inbox/recent.md", {**done, "finished": "2026-10-29"}
    )
    write_task_note(test_vault, "00-Inbox/edge.md", {**done, "finished": "2026-10-28"})
    write_task_note(test_vault, "00-Inbox/old.md", {**done, "finished": "2026-10-27"})
    fresh = write_task_note(test_vault, "00-Inbox/no-finished-fresh.md", done)
    stale = write_task_note(test_vault, "00-Inbox/no-finished-stale.md", done)
    now = datetime(2026, 11, 3).timestamp()
    os.utime(fresh, (now, now))
    old = datetime(2026, 10, 1).timestamp()
    os.utime(stale, (old, old))

    assert titles(make_backend(test_vault)) == {"recent", "edge", "no-finished-fresh"}


def test_unreadable_notes_are_skipped_and_named(test_vault: Path):
    write_task_note(test_vault, "00-Inbox/good.md")
    (test_vault / "00-Inbox/binary.md").write_bytes(b"---\ntype: task\n\xff\xfe\n---\n")
    (test_vault / "00-Inbox/malformed.md").write_text(
        "---\ntype: task\nstatus: [unclosed\n---\n", encoding="utf-8"
    )
    backend = make_backend(test_vault)

    assert titles(backend) == {"good"}
    warnings = backend.get_warnings()
    assert len(warnings) == 2
    assert any("00-Inbox/binary.md" in w for w in warnings)
    assert any("00-Inbox/malformed.md" in w for w in warnings)


def test_lookups_use_the_last_scan_and_ids_are_stable(test_vault: Path):
    path = write_task_note(test_vault, "00-Inbox/a.md", {"status": "pending"})
    write_task_note(test_vault, "00-Inbox/b.md", {"status": "pending"})
    backend = make_backend(test_vault)
    first = {t.title: t for t in backend.get_tasks_on_active_board()}

    path.write_text("---\ntype: task\nstatus: active\n---\n# Changed\n", "utf-8")

    looked_up = backend.get_task_by_id(first["a"].task_id)
    assert looked_up is not None
    assert looked_up.title == "a"
    assert looked_up.column == 1
    both = backend.get_tasks_by_ids([first["a"].task_id, first["b"].task_id])
    assert {t.title for t in both} == {"a", "b"}

    write_task_note(test_vault, "00-Inbox/c.md")
    second = {t.title: t for t in backend.get_tasks_on_active_board()}

    assert second["b"].task_id == first["b"].task_id
    assert second["Changed"].task_id == first["a"].task_id
    assert second["c"].task_id not in {first["a"].task_id, first["b"].task_id}
    assert backend.get_task_by_id(9999) is None
