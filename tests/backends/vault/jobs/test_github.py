import json
import subprocess

import pytest

from kanban_tui.backends.vault.jobs.github import (
    GhPrStates,
    PrFetchError,
    PrRef,
    parse_pr_url,
)

URL = "https://github.com/Acme/app/pull/7"


class RecordingRunner:
    def __init__(self, responses: dict[str, tuple[int, str, str]]):
        self.responses = responses
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(
        self, argv: list[str], env: dict[str, str], timeout: float
    ) -> tuple[int, str, str]:
        self.calls.append((argv, env))
        key = next(k for k in self.responses if " ".join(argv).startswith(k))
        return self.responses[key]


def gh_runner(state_output: tuple[int, str, str]) -> RecordingRunner:
    return RecordingRunner(
        {
            "gh auth token --user": (0, "tok-work\n", ""),
            "gh pr view": state_output,
        }
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r/pull/12",
        "https://github.com/o/r/pull/12/",
        "https://github.com/o/r/pull/12/files",
        "https://github.com/o/r/pull/12?diff=split",
        "https://github.com/o/r/pull/12#issuecomment-1",
    ],
)
def test_parse_pr_url_reads_owner_repo_and_number(url: str):
    assert parse_pr_url(url) == PrRef("o", "r", 12)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r/issues/12",
        "https://gitlab.com/o/r/pull/12",
        "not a url",
        "https://github.com/o/r/pull/abc",
    ],
)
def test_parse_pr_url_rejects_anything_else(url: str):
    assert parse_pr_url(url) is None


@pytest.mark.parametrize("accounts", [{"acme": "work"}, {"ACME": "work"}])
def test_listed_owner_uses_the_account_token_once_per_account(
    accounts: dict[str, str],
):
    runner = gh_runner((0, json.dumps({"state": "MERGED"}), ""))
    states = GhPrStates(accounts, runner)

    assert states.state(URL) == "MERGED"
    assert states.state(URL) == "MERGED"

    auth_calls = [c for c in runner.calls if c[0][:3] == ["gh", "auth", "token"]]
    assert [c[0] for c in auth_calls] == [["gh", "auth", "token", "--user", "work"]]
    view_calls = [c for c in runner.calls if c[0][:3] == ["gh", "pr", "view"]]
    assert len(view_calls) == 2
    assert view_calls[0][0] == ["gh", "pr", "view", URL, "--json", "state"]
    assert view_calls[0][1] == {"GH_TOKEN": "tok-work"}


def test_unlisted_owner_runs_gh_without_a_token_override():
    runner = gh_runner((0, json.dumps({"state": "OPEN"}), ""))

    assert GhPrStates({"someone-else": "x"}, runner).state(URL) == "OPEN"

    assert [c[0][:3] for c in runner.calls] == [["gh", "pr", "view"]]
    assert runner.calls[0][1] == {}


@pytest.mark.parametrize(
    "output",
    [
        (1, "", "no such pr"),
        (0, "not json", "garbled"),
        (0, json.dumps({"state": "DRAFT"}), "odd state"),
        (0, json.dumps({}), "no state"),
    ],
)
def test_bad_gh_output_raises_with_stderr(output: tuple[int, str, str]):
    states = GhPrStates({}, gh_runner(output))

    with pytest.raises(PrFetchError, match=output[2]):
        states.state(URL)


def test_failed_token_lookup_raises_with_stderr():
    runner = RecordingRunner({"gh auth token --user": (1, "", "no such account")})

    with pytest.raises(PrFetchError, match="no such account"):
        GhPrStates({"acme": "work"}, runner).state(URL)


def test_timeout_raises_fetch_error():
    def timing_out(argv, env, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    with pytest.raises(PrFetchError, match="timed out"):
        GhPrStates({}, timing_out).state(URL)


def test_pr_url_that_is_not_github_raises():
    with pytest.raises(PrFetchError):
        GhPrStates({}, gh_runner((0, "{}", ""))).state("https://example.com/x")


def test_missing_gh_raises_fetch_error():
    def missing(argv, env, timeout):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    with pytest.raises(PrFetchError, match="cannot run gh"):
        GhPrStates({}, missing).state(URL)


@pytest.mark.parametrize(
    "output",
    [(0, "not json", ""), (0, json.dumps({"state": "DRAFT"}), "")],
)
def test_fetch_error_message_has_no_dangling_separator(output: tuple[int, str, str]):
    with pytest.raises(PrFetchError) as raised:
        GhPrStates({}, gh_runner(output)).state(URL)

    assert not str(raised.value).rstrip().endswith(":")
