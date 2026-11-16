from __future__ import annotations

from pathlib import Path

from kanban_tui.backends.vault.open_note import NoteOpenerApp


def launch_session(
    app: NoteOpenerApp, folder: Path, title: str, note_path: str
) -> bool:
    """Open a background kitty tab running tackle-task on a vault note.

    The tab runs `claude "/vault-pkm:tackle-task <note_path>"` in `folder`,
    titled `title`, without taking focus.

    Returns:
        True when kitty accepted the launch. Otherwise the app is notified
        with an error and nothing starts.
    """
    raise NotImplementedError
