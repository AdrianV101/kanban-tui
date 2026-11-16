from collections.abc import Iterable
from pathlib import Path

from textual.screen import ModalScreen
from textual.widget import Widget


class ModalSessionFolderScreen(ModalScreen[Path | None]):
    """Asks which folder a session on an unlinked task starts in.

    With a `project`, it says that running `/vault-pkm:init-project` in the
    project's repo skips this question next time. Dismisses with the chosen
    folder, `~` expanded, or with None on Escape.
    """

    def __init__(self, project: str | None, suggestions: list[str]) -> None:
        self.project = project
        self.suggestions = suggestions
        super().__init__()

    def compose(self) -> Iterable[Widget]:
        yield from ()
