from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from kanban_tui.backends.vault.open_note import NoteOpenerApp

KITTY_APP_BINARY = Path("/Applications/kitty.app/Contents/MacOS/kitty")
LAUNCH_TIMEOUT_SECONDS = 10
KITTY_SETUP = (
    "Starting a session needs the board running in kitty with remote control on. "
    "Add these lines to ~/.config/kitty/kitty.conf, then restart kitty: "
    "allow_remote_control socket-only, listen_on unix:/tmp/kitty"
)


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
    if not (os.environ.get("KITTY_WINDOW_ID") and os.environ.get("KITTY_LISTEN_ON")):
        app.notify(KITTY_SETUP, severity="error")
        return False
    kitty = find_program("kitty", KITTY_APP_BINARY)
    if kitty is None:
        app.notify("kitty was not found, so no session started.", severity="error")
        return False
    claude = find_program("claude", Path.home() / ".local" / "bin" / "claude")
    if claude is None:
        app.notify(
            "Claude Code was not found, so no session started.", severity="error"
        )
        return False
    argv = [kitty, "@", "launch", "--type=tab", "--keep-focus", "--copy-env"]
    argv += ["--tab-title", title, "--cwd", folder.as_posix()]
    argv += [claude, f"/vault-pkm:tackle-task {note_path}"]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=LAUNCH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        app.notify(f"kitty could not open the session tab: {error}", severity="error")
        return False
    if result.returncode != 0:
        app.notify(
            f"kitty could not open the session tab: {result.stderr.strip()}",
            severity="error",
        )
        return False
    return True


def find_program(name: str, fallback: Path) -> str | None:
    """The program on PATH, else `fallback` when that file exists."""
    found = shutil.which(name)
    if found:
        return found
    return fallback.as_posix() if fallback.is_file() else None
