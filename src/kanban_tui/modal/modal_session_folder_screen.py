from collections.abc import Iterable
from pathlib import Path

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Input, Label


class ModalSessionFolderScreen(ModalScreen[Path | None]):
    """Asks which folder a session on an unlinked task starts in.

    With a `project`, it says that running `/vault-pkm:init-project` in the
    project's repo skips this question next time. Dismisses with the chosen
    folder, `~` expanded, or with None on Escape.
    """

    BINDINGS = [Binding("escape", "cancel", "Close")]

    def __init__(self, project: str | None, suggestions: list[str]) -> None:
        self.project = project
        self.suggestions = suggestions
        super().__init__()

    def compose(self) -> Iterable[Widget]:
        with Vertical():
            yield Label(self.hint(), id="session_hint")
            yield Input(
                placeholder="Folder to start the session in",
                suggester=SuggestFromList(self.suggestions, case_sensitive=False),
                id="session_folder",
            )
            yield Label("", id="session_error")

    def hint(self) -> str:
        if self.project is None:
            return "This task has no project. Pick a folder for this session."
        return (
            f"{self.project} has no linked repo. Pick a folder for this session. "
            "To skip this question next time, run /vault-pkm:init-project "
            "in the project's repo."
        )

    @on(Input.Submitted)
    def choose_folder(self, event: Input.Submitted) -> None:
        typed = event.value.strip()
        folder = Path(typed).expanduser()
        if not typed or not folder.is_dir():
            self.query_one("#session_error", Label).update(
                f"'{typed}' is not a folder. Type an existing folder."
            )
            return
        self.dismiss(folder)

    def action_cancel(self) -> None:
        self.dismiss(None)


def folder_suggestions(root: str) -> list[str]:
    """The folders directly under `root`, written from `~` when under home."""
    expanded = Path(root).expanduser()
    if not expanded.is_dir():
        return []
    home = Path.home()
    suggestions = []
    for child in sorted(expanded.iterdir()):
        if not child.is_dir():
            continue
        if child.is_relative_to(home):
            suggestions.append(f"~/{child.relative_to(home).as_posix()}")
        else:
            suggestions.append(child.as_posix())
    return suggestions
