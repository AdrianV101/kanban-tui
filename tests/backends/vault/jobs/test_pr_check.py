from datetime import date
from pathlib import Path

import pytest

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.jobs.github import GhPrStates, PrFetchError, PrState
from kanban_tui.backends.vault.jobs.pr_check import check_prs
from kanban_tui.config import VaultBackendSettings, VaultBoard
from tests.conftest import write_task_note

TODAY = date.today()
NOTE = "01-Projects/Alpha/tasks/card.md"
OTHER = "01-Projects/Alpha/tasks/other.md"
LINE = (
    f"- {TODAY}: every PR in `prs` closed without merging. "
    "The PR check moved this card back to Doing."
)


def make_backend(vault: Path) -> VaultBackend:
    return VaultBackend(VaultBackendSettings(vault_path=vault.as_posix()))


def prs_field(urls: list[str]) -> str:
    return "\n" + "\n".join(f"  - {u}" for u in urls)


def url(n: int) -> str:
    return f"https://github.com/o/r/pull/{n}"


def in_review(vault: Path, rel: str, urls: list[str], **extra: object) -> Path:
    fields: dict[str, object] = {
        "status": "active",
        "board": "in-review",
        "prs": prs_field(urls) if urls else None,
    }
    fields.update(extra)
    return write_task_note(vault, rel, fields, body="body\n")


class FakeFetch:
    def __init__(self, states: dict[str, PrState | Exception]):
        self.states = states
        self.calls: list[str] = []

    def __call__(self, pr_url: str) -> PrState:
        self.calls.append(pr_url)
        result = self.states[pr_url]
        if isinstance(result, Exception):
            raise result
        return result


def columns(vault: Path) -> dict[str, int]:
    return {
        t.metadata["note_path"]: t.column
        for t in make_backend(vault).get_tasks_on_active_board()
    }


@pytest.mark.parametrize(
    "states,outcome",
    [
        (["OPEN"], "same"),
        (["OPEN", "MERGED"], "same"),
        (["MERGED"], "done"),
        (["CLOSED", "MERGED"], "done"),
        (["CLOSED"], "doing"),
        (["CLOSED", "CLOSED"], "doing"),
    ],
)
def test_decision_rule(test_vault: Path, states: list[PrState], outcome: str):
    urls = [url(i + 1) for i in range(len(states))]
    path = in_review(test_vault, NOTE, urls)
    before = path.read_bytes()
    fetch = FakeFetch(dict(zip(urls, states)))

    report = check_prs(make_backend(test_vault), fetch, TODAY)

    after = path.read_text()
    assert report.ok
    assert report.skipped == []
    if outcome == "same":
        assert path.read_bytes() == before
        assert (report.done, report.reopened) == ([], [])
        assert columns(test_vault)[NOTE] == 4
    elif outcome == "done":
        assert "status: done" in after
        assert f"finished: {TODAY}" in after
        assert report.done == [NOTE]
        assert columns(test_vault)[NOTE] == 5
    else:
        assert "status: active" in after
        assert "board: doing" in after
        assert after.rstrip("\n").splitlines()[-1] == LINE
        assert report.reopened == [NOTE]
        assert columns(test_vault)[NOTE] == 3


def test_only_in_review_cards_are_checked_and_shared_urls_fetched_once(
    test_vault: Path,
):
    in_review(test_vault, NOTE, [url(1)])
    in_review(test_vault, OTHER, [url(1)])
    for i, board in enumerate(["proposed", "ready", "doing"]):
        write_task_note(
            test_vault,
            f"01-Projects/Alpha/tasks/c{i}.md",
            {
                "status": "active" if board == "doing" else "pending",
                "board": board,
                "prs": prs_field([url(50 + i)]),
            },
        )
    write_task_note(
        test_vault,
        "01-Projects/Alpha/tasks/done.md",
        {"status": "done", "finished": TODAY, "prs": prs_field([url(60)])},
    )
    fetch = FakeFetch({url(1): "MERGED"})

    report = check_prs(make_backend(test_vault), fetch, TODAY)

    assert fetch.calls == [url(1)]
    assert sorted(report.done) == sorted([NOTE, OTHER])


def test_in_review_cards_off_the_active_board_are_still_checked(test_vault: Path):
    acme_note = "01-Projects/Acme/tasks/card.md"
    in_review(test_vault, NOTE, [url(1)])
    in_review(test_vault, acme_note, [url(2)])
    backend = VaultBackend(
        VaultBackendSettings(
            vault_path=test_vault.as_posix(),
            boards=[VaultBoard(name="Personal", exclude_projects=["Acme"])],
            active_board="Personal",
        )
    )

    report = check_prs(backend, FakeFetch({url(1): "MERGED", url(2): "MERGED"}), TODAY)

    assert sorted(report.done) == sorted([NOTE, acme_note])


@pytest.mark.parametrize(
    "prs_value,fetch_states",
    [
        (None, {}),
        ("\n  - 7", {}),
        (prs_field(["https://example.com/x"]), {}),
        (prs_field([url(1), url(2)]), {url(1): "MERGED", url(2): PrFetchError("boom")}),
    ],
)
def test_skips_leave_the_note_alone_and_do_not_stop_others(
    test_vault: Path, prs_value: str | None, fetch_states: dict
):
    skipped_path = write_task_note(
        test_vault,
        NOTE,
        {"status": "active", "board": "in-review", "prs": prs_value},
        body="body\n",
    )
    in_review(test_vault, OTHER, [url(9)])
    before = skipped_path.read_bytes()
    fetch = FakeFetch({**fetch_states, url(9): "MERGED"})

    report = check_prs(make_backend(test_vault), fetch, TODAY)

    assert skipped_path.read_bytes() == before
    assert [path for path, _ in report.skipped] == [NOTE]
    assert report.skipped[0][1]
    assert report.done == [OTHER]
    assert not report.ok


def test_concurrent_move_is_refused_and_reported(test_vault: Path):
    path = in_review(test_vault, NOTE, [url(1)])

    def edit_then_merged(pr_url: str) -> PrState:
        path.write_text(path.read_text().replace("in-review", "doing"))
        return "MERGED"

    report = check_prs(make_backend(test_vault), edit_then_merged, TODAY)

    assert "board: doing" in path.read_text()
    assert "status: done" not in path.read_text()
    assert report.done == []
    assert [p for p, _ in report.skipped] == [NOTE]
    assert not report.ok


def test_missing_gh_skips_each_card_with_a_reason_and_keeps_going(test_vault: Path):
    def missing(argv, env, timeout):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    gh = GhPrStates({}, missing)
    first = in_review(test_vault, NOTE, [url(1)])
    in_review(test_vault, OTHER, [url(2)])
    before = first.read_bytes()

    report = check_prs(make_backend(test_vault), gh.state, TODAY)

    assert first.read_bytes() == before
    assert sorted(path for path, _ in report.skipped) == [NOTE, OTHER]
    assert all("cannot run gh" in reason for _, reason in report.skipped)
    assert not report.ok
