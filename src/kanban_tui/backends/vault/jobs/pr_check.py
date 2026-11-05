from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.jobs.github import PrFetchError, PrState, parse_pr_url
from kanban_tui.classes.task import Task

DOING_COLUMN = 3
IN_REVIEW_COLUMN = 4
DONE_COLUMN = 5


@dataclass
class PrCheckReport:
    done: list[str] = field(default_factory=list)
    reopened: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.skipped


def check_prs(
    backend: VaultBackend, fetch: Callable[[str], PrState], today: date
) -> PrCheckReport:
    """Move In Review cards whose PRs have all closed.

    Any merged PR sends the card to Done. All closed unmerged sends it back to
    Doing with a note line. A card with an open or unreadable PR is left alone.
    """
    report = PrCheckReport()
    fetched: dict[str, PrState] = {}
    for task in backend.get_tasks_on_active_board():
        if task.metadata["column"] != IN_REVIEW_COLUMN:
            continue
        path = task.metadata["note_path"]
        try:
            states = _card_states(task, fetch, fetched)
        except PrFetchError as error:
            report.skipped.append((path, str(error)))
            continue
        if "OPEN" in states:
            continue
        if "MERGED" in states:
            result = backend.update_task_status(_moved(task, DONE_COLUMN))
            target = report.done
        else:
            result = backend.move_with_note(
                _moved(task, DOING_COLUMN), DOING_COLUMN, _reopen_line(today)
            )
            target = report.reopened
        if isinstance(result, dict):
            report.skipped.append((path, result["message"]))
        else:
            target.append(path)
    return report


def _card_states(
    task: Task, fetch: Callable[[str], PrState], fetched: dict[str, PrState]
) -> list[PrState]:
    urls: list[str] = task.metadata["prs"]
    if not urls:
        raise PrFetchError("no readable PR links in prs")
    for url in urls:
        if parse_pr_url(url) is None:
            raise PrFetchError(f"not a GitHub PR link: {url}")
    for url in urls:
        if url not in fetched:
            fetched[url] = fetch(url)
    return [fetched[url] for url in urls]


def _moved(task: Task, column: int) -> Task:
    return task.model_copy(update={"column": column, "metadata": dict(task.metadata)})


def _reopen_line(today: date) -> str:
    return (
        f"- {today}: every PR in `prs` closed without merging. "
        "The PR check moved this card back to Doing."
    )
