from pathlib import Path

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.config import VaultBackendSettings
from tests.conftest import write_task_note


def make_backend(vault: Path) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix()))


def test_archiving_keeps_the_note(tmp_path: Path):
    vault = tmp_path / "PKM"
    note = write_task_note(
        vault, "01-Projects/Alpha/tasks/note.md", {"status": "active"}
    )
    backend = make_backend(vault)
    (task,) = backend.get_tasks_on_active_board()

    backend.delete_task(task.task_id)

    assert note.exists()
    assert "\nstatus: cancelled\n" in note.read_text()
    visible = {c.column_id for c in backend.get_columns() if c.visible}
    assert [t for t in backend.get_tasks_on_active_board() if t.column in visible] == []


def test_the_obsidian_link_encodes_vault_and_path(tmp_path: Path):
    vault = tmp_path / "PKM"
    write_task_note(vault, "01-Projects/Next Steps/tasks/a b.md")
    backend = make_backend(vault)
    (task,) = backend.get_tasks_on_active_board()

    assert backend.note_url(task) == (
        "obsidian://open?vault=PKM&file=01-Projects%2FNext%20Steps%2Ftasks%2Fa%20b"
    )
