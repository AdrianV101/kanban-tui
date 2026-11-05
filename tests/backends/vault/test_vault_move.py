import os
from pathlib import Path

import pytest
from freezegun import freeze_time

from kanban_tui.backends.vault import backend as backend_module
from kanban_tui.backends.vault.backend import VaultBackend
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
@pytest.mark.parametrize(
    "start,column,status,board",
    [
        ({"status": "done", "finished": FROZEN_DAY}, 1, "pending", "proposed"),
        ({"status": "done", "finished": FROZEN_DAY}, 2, "pending", "ready"),
        (
            {"status": "pending", "board": "ready"},
            3,
            "active",
            "doing",
        ),
        ({"status": "pending"}, 4, "active", "in-review"),
        (
            {"status": "active", "board": "doing"},
            5,
            "done",
            "doing",
        ),
        (
            {"status": "active", "board": "doing"},
            6,
            "cancelled",
            "doing",
        ),
        (
            {"status": "done", "board": "ready", "finished": FROZEN_DAY},
            2,
            "pending",
            "ready",
        ),
        ({"status": "active"}, 5, "done", None),
        ({"status": "active"}, 6, "cancelled", None),
    ],
)
def test_a_move_writes_the_columns_fields(
    test_vault: Path,
    start: dict[str, str],
    column: int,
    status: str,
    board: str | None,
):
    path = write_task_note(test_vault, NOTE, start)
    backend = make_backend(test_vault)

    move_only_card(backend, column)

    text = path.read_text()
    assert f"\nstatus: {status}\n" in text
    if board is None:
        assert "\nboard:" not in text
    else:
        assert f"\nboard: {board}\n" in text
    (task,) = backend.get_tasks_on_active_board()
    assert task.column == column
    assert task.metadata["status"] == status
    assert task.metadata["board"] == board
    assert task.metadata["column"] == column


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "original,expected",
    [
        (
            "---\ntype: task\nstatus: pending\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            '---\ntype: task\nstatus: "pending"\n---\nbody\n',
            '---\ntype: task\nstatus: "active"\nboard: doing\n---\nbody\n',
        ),
        (
            "---\ntype: task\nstatus: pending  # note\n---\nbody\n",
            "---\ntype: task\nstatus: active  # note\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\n---\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\n",
        ),
        (
            "---\ntype: task\nstatus:\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: \n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: # c\n---\nbody\n",
            "---\ntype: task\nstatus: active # c\nboard: doing\n---\nbody\n",
        ),
        (
            (
                "---\ntype: task\ntags:\n  - a\n  - b\nstatus: pending\n---\n"
                "# T\n\n- [[Some Note]]\n- [[Other|alias]]\n"
            ),
            (
                "---\ntype: task\ntags:\n  - a\n  - b\nstatus: active\nboard: doing\n"
                "---\n# T\n\n- [[Some Note]]\n- [[Other|alias]]\n"
            ),
        ),
        (
            "---\ntype: task\nstatus: pending\n---\nno trailing newline",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nno trailing newline",
        ),
        (
            "---\r\ntype: task\r\nstatus: pending\r\n---\r\nbody\r\n",
            "---\r\ntype: task\r\nstatus: active\r\nboard: doing\r\n---\r\nbody\r\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nboard: doing\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nboard: ready\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            '---\ntype: task\nstatus: pending\nboard: "ready"\n---\nbody\n',
            '---\ntype: task\nstatus: active\nboard: "doing"\n---\nbody\n',
        ),
        (
            "---\ntype: task\nstatus: pending\nboard: ready  # note\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing  # note\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nboard:\n---\nbody\n",
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nprs: []\n---\nbody\n",
            "---\ntype: task\nstatus: active\nprs: []\nboard: doing\n---\nbody\n",
        ),
    ],
)
def test_only_the_owned_lines_change(test_vault: Path, original: str, expected: str):
    path = write_raw(test_vault, original)

    move_only_card(make_backend(test_vault), 3)

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

    move_only_card(make_backend(test_vault), 5)

    assert path.read_bytes().decode() == expected


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "original,column,expected",
    [
        (
            "---\ntype: task\nstatus: done\nfinished: 2026-11-01\n---\nbody\n",
            1,
            "---\ntype: task\nstatus: pending\nboard: proposed\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: done\nfinished: 2026-11-01\nboard: doing\n---\nbody\n",
            3,
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
        (
            "---\ntype: task\nstatus: done\nfinished: 2026-11-01\n---\nbody\n",
            6,
            "---\ntype: task\nstatus: cancelled\n---\nbody\n",
        ),
        (
            "---\r\ntype: task\r\nstatus: done\r\nfinished: 2026-11-01\r\n---\r\nbody\r\n",
            2,
            "---\r\ntype: task\r\nstatus: pending\r\nboard: ready\r\n---\r\nbody\r\n",
        ),
        (
            "---\ntype: task\nstatus: pending\nfinished: 2020-01-01\n---\nbody\n",
            3,
            "---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n",
        ),
    ],
)
def test_leaving_done_removes_the_finished_line(
    test_vault: Path, original: str, column: int, expected: str
):
    path = write_raw(test_vault, original)

    move_only_card(make_backend(test_vault), column)

    assert path.read_bytes().decode() == expected


@pytest.mark.parametrize(
    "start,old,new,named",
    [
        ({"status": "pending"}, "pending", "active", "status 'active'"),
        (
            {"status": "pending", "board": "ready"},
            "board: ready",
            "board: proposed",
            "board 'proposed'",
        ),
    ],
)
def test_a_changed_column_on_disk_refuses_the_move(
    test_vault: Path, start: dict[str, str], old: str, new: str, named: str
):
    path = write_task_note(test_vault, NOTE, start)
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    path.write_text(path.read_text().replace(old, new))
    before = path.read_bytes()
    task.column = 3

    result = backend.update_task_status(task)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert named in result["message"]
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
    task.column = 3

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
    task.column = 3

    result = backend.update_task_status(task)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert sorted(test_vault.rglob("*")) == files_before


@pytest.mark.parametrize("when", ["after_read", "before_replace"])
def test_a_status_written_during_the_move_is_not_overwritten(
    test_vault: Path, monkeypatch: pytest.MonkeyPatch, when: str
):
    path = write_task_note(test_vault, NOTE, {"status": "pending"})
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    task.column = 3
    changed: list[bool] = []

    def change_note_once() -> None:
        if changed:
            return
        changed.append(True)
        original = Path.read_bytes(path)
        path.write_bytes(original.replace(b"pending", b"cancelled"))

    if when == "after_read":
        real_read_bytes = Path.read_bytes
        real_read_text = Path.read_text

        def read_bytes(self: Path) -> bytes:
            data = real_read_bytes(self)
            if self == path:
                change_note_once()
            return data

        def read_text(self: Path, *args, **kwargs) -> str:
            text = real_read_text(self, *args, **kwargs)
            if self == path:
                change_note_once()
            return text

        monkeypatch.setattr(Path, "read_bytes", read_bytes)
        monkeypatch.setattr(Path, "read_text", read_text)
    else:
        real_chmod = os.chmod

        def chmod(target, mode):
            change_note_once()
            real_chmod(target, mode)

        monkeypatch.setattr(backend_module.os, "chmod", chmod)

    result = backend.update_task_status(task)

    monkeypatch.undo()
    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert "\nstatus: cancelled\n" in path.read_text()
    assert not list(path.parent.glob("*.tmp"))


def test_the_new_content_is_flushed_to_disk_before_it_replaces_the_note(
    test_vault: Path, monkeypatch: pytest.MonkeyPatch
):
    write_task_note(test_vault, NOTE, {"status": "pending"})
    backend = make_backend(test_vault)
    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        calls.append("fsync")
        real_fsync(fd)

    def replace(source, target):
        calls.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(backend_module.os, "fsync", fsync)
    monkeypatch.setattr(backend_module.os, "replace", replace)

    move_only_card(backend, 3)

    assert calls == ["fsync", "replace"]


def test_a_symlinked_note_refuses_the_move_and_stays_a_link(test_vault: Path):
    target = test_vault.parent / "elsewhere.md"
    target.write_text("---\ntype: task\nstatus: pending\n---\nbody\n")
    link = test_vault / NOTE
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    backend = make_backend(test_vault)

    result = move_only_card(backend, 3)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert NOTE in result["message"]
    assert link.is_symlink()
    assert "status: pending" in target.read_text()


LINE = "- 2026-11-04 PR closed without merge"


def move_with_line(backend: VaultBackend, column: int, line: str = LINE):
    (task,) = backend.get_tasks_on_active_board()
    return backend.move_with_note(task, column, line)


@freeze_time(FROZEN_DAY)
@pytest.mark.parametrize(
    "original,expected",
    [
        (
            "---\ntype: task\nstatus: active\nboard: in-review\n---\nbody\n",
            f"---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n{LINE}\n",
        ),
        (
            "---\ntype: task\nstatus: active\nboard: in-review\n---\nbody",
            f"---\ntype: task\nstatus: active\nboard: doing\n---\nbody\n{LINE}\n",
        ),
        (
            "---\r\ntype: task\r\nstatus: active\r\nboard: in-review\r\n---\r\nbody\r\n",
            f"---\r\ntype: task\r\nstatus: active\r\nboard: doing\r\n---\r\nbody\r\n{LINE}\r\n",
        ),
        (
            "---\r\ntype: task\r\nstatus: active\r\nboard: in-review\r\n---\r\nbody",
            f"---\r\ntype: task\r\nstatus: active\r\nboard: doing\r\n---\r\nbody\r\n{LINE}\r\n",
        ),
    ],
)
def test_a_move_with_a_note_line_writes_fields_and_the_last_line(
    test_vault: Path, original: str, expected: str
):
    path = write_raw(test_vault, original)
    backend = make_backend(test_vault)

    result = move_with_line(backend, 3)

    assert path.read_bytes() == expected.encode()
    assert not isinstance(result, dict)
    assert result.column == 3
    (task,) = backend.get_tasks_on_active_board()
    assert task.column == 3


@freeze_time(FROZEN_DAY)
def test_a_move_with_a_note_line_to_done_stamps_finished(test_vault: Path):
    path = write_raw(test_vault, "---\ntype: task\nstatus: active\n---\nbody\n")

    move_with_line(make_backend(test_vault), 5)

    assert path.read_text() == (
        f"---\ntype: task\nstatus: done\nfinished: {FROZEN_DAY}\n---\nbody\n{LINE}\n"
    )


def test_a_move_with_a_note_line_is_refused_when_the_column_changed_on_disk(
    test_vault: Path,
):
    path = write_raw(
        test_vault, "---\ntype: task\nstatus: active\nboard: in-review\n---\nbody\n"
    )
    backend = make_backend(test_vault)
    (task,) = backend.get_tasks_on_active_board()
    changed = "---\ntype: task\nstatus: pending\nboard: ready\n---\nbody\n"
    path.write_bytes(changed.encode())

    result = backend.move_with_note(task, 3, LINE)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert path.read_bytes() == changed.encode()
