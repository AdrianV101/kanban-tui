from __future__ import annotations

import subprocess
import sys
from typing import Protocol

from textual.notifications import SeverityLevel


class NoteOpenerApp(Protocol):
    @property
    def is_web(self) -> bool: ...

    def open_url(self, url: str) -> None: ...

    def notify(self, message: str, *, severity: SeverityLevel = ...) -> None: ...


def open_note(app: NoteOpenerApp, url: str) -> None:
    """Open a note's obsidian:// URL in Obsidian.

    On macOS, Python's webbrowser sends non-web URLs to the default browser,
    so a terminal app hands the URL to the system instead. A web app still uses
    open_url, which opens the URL on the viewer's machine.
    """
    if sys.platform != "darwin" or app.is_web:
        app.open_url(url)
        return
    result = subprocess.run(
        ["/usr/bin/open", url], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        app.notify(
            f"Could not open the note: {result.stderr.strip()}", severity="error"
        )
