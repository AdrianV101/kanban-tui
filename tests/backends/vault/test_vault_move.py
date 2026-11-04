from pathlib import Path

import pytest
from freezegun import freeze_time

from kanban_tui.backends.vault.backend import STATUS_COLUMNS, VaultBackend
from kanban_tui.config import VaultBackendSettings
from tests.conftest import write_task_note

NOTE = "01-Projects/Alpha/tasks/note.md"
FROZEN_DAY = "2026-11-04"


def make_backend(vault: Path) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix()))


def write_raw(vault: Path, content: str) -> Path:
    path = vault / NOTE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode())
    return path


def move_only_card(backend: VaultBackend, column: int):
    (task,) = backend.get_tasks_on_active_board()
    task.column = column
    return backend.update_task_status(task)


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize("status,column", list(STATUS_COLUMNS.items()))
def test_a_move_writes_the_columns_status(test_vault: Path, status: str, column: int):
    start = "done" if status == "proposed" else "proposed"
    write_task_note(test_vault, NOTE, {"status": start, "finished": FROZEN_DAY})
    backend = make_backend(test_vault)

    move_only_card(backend, column)

    (task,) = backend.get_tasks_on_active_board()
    assert task.column == column
    assert task.metadata["status"] == status
    assert f"\nstatus: {status}\n" in (test_vault / NOTE).read_text()


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "original,expected",
    [
        (
            "---\ntype: task\nstatus: pending\n---\nbody\n",
            "---\ntype: task\nstatus: active\n---\nbody\n",
        ),
        (
            '---\ntype: task\nstatus: "pending"\n---\nbody\n',
            '---\ntype: task\nstatus: "active"\n---\nbody\n',
        ),
        (
            "---\ntype: task\nstatus: pending  # note\n---\nbody\n",
            "---\ntype: task\nstatus: active  # note\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\n---\n",
            "---\ntype: task\nstatus: active\n---\n",
        ),
        (
            "---\ntype: task\nstatus:\n---\nbody\n",
            "---\ntype: task\nstatus: active\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: \n---\nbody\n",
            "---\ntype: task\nstatus: active\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: # c\n---\nbody\n",
            "---\ntype: task\nstatus: active # c\n---\nbody\n",
        ),
        (
            (
                "---\ntype: task\ntags:\n  - a\n  - b\nstatus: pending\n---\n"
                "# T\n\n- [[Some Note]]\n- [[Other|alias]]\n"
            ),
            (
                "---\ntype: task\ntags:\n  - a\n  - b\nstatus: active\n---\n"
                "# T\n\n- [[Some Note]]\n- [[Other|alias]]\n"
            ),
        ),
        (
            "---\ntype: task\nstatus: pending\n---\nno trailing newline",
            "---\ntype: task\nstatus: active\n---\nno trailing newline",
        ),
        (
            "---\r\ntype: task\r\nstatus: pending\r\n---\r\nbody\r\n",
            "---\r\ntype: task\r\nstatus: active\r\n---\r\nbody\r\n",
        ),
    ],
)
def test_only_the_status_line_changes(test_vault: Path, original: str, expected: str):
    path = write_raw(test_vault, original)

    move_only_card(make_backend(test_vault), STATUS_COLUMNS["active"])

    assert path.read_bytes().decode() == expected


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "original,expected",
    [
        (
            "---\ntype: task\nstatus: pending\n---\nbody\n",
            "---\ntype: task\nstatus: done\nfinished: 2026-11-04\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nfinished: 2020-01-01\n---\nbody\n",
            "---\ntype: task\nstatus: done\nfinished: 2026-11-04\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\n---",
            "---\ntype: task\nstatus: done\nfinished: 2026-11-04\n---",
        ),
        (
            "---\r\ntype: task\r\nstatus: pending\r\n---\r\nbody\r\n",
            "---\r\ntype: task\r\nstatus: done\r\nfinished: 2026-11-04\r\n---\r\nbody\r\n",
        ),
    ],
)
def test_entering_done_adds_only_the_finished_line(
    test_vault: Path, original: str, expected: str
):
    path = write_raw(test_vault, original)

    move_only_card(make_backend(test_vault), STATUS_COLUMNS["done"])

    assert path.read_bytes().decode() == expected


def test_a_changed_status_on_disk_refuses_the_move(test_vault: Path):
    path = write_task_note(test_vault, NOTE, {"status": "pending"})
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    path.write_text(path.read_text().replace("pending", "in-review"))
    before = path.read_bytes()
    task.column = STATUS_COLUMNS["active"]

    result = backend.update_task_status(task)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert path.read_bytes() == before


def test_other_changes_on_disk_are_kept(test_vault: Path):
    path = write_task_note(test_vault, NOTE, {"status": "pending"}, body="# Old\n")
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    path.write_text(
        path.read_text()
        .replace("# Old", "# New body")
        .replace("type: task", "type: task\npriority: high")
    )
    task.column = STATUS_COLUMNS["active"]

    backend.update_task_status(task)

    text = path.read_text()
    assert "\nstatus: active\n" in text
    assert "# New body" in text
    assert "priority: high" in text


@pytest.mark.parametrize("how", ["deleted", "renamed"])
def test_a_missing_note_refuses_the_move(test_vault: Path, how: str):
    path = write_task_note(test_vault, NOTE, {"status": "pending"})
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    if how == "deleted":
        path.unlink()
    else:
        path.rename(path.with_name("renamed.md"))
    files_before = sorted(test_vault.rglob("*"))
    task.column = STATUS_COLUMNS["active"]

    result = backend.update_task_status(task)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert sorted(test_vault.rglob("*")) == files_before
