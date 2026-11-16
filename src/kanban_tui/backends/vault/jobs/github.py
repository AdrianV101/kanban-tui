from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Literal, get_args

from kanban_tui.backends.vault.jobs.runner import Runner, run_command

PrState = Literal["OPEN", "CLOSED", "MERGED"]
GH_TIMEOUT_SECONDS = 30

_PR_URL = re.compile(
    r"^https://github\.com/(?P<owner>[^/?#]+)/(?P<repo>[^/?#]+)"
    r"/pull/(?P<number>\d+)(?:[/?#].*)?$"
)


class PrFetchError(Exception):
    pass


@dataclass(frozen=True)
class PrRef:
    owner: str
    repo: str
    number: int


def parse_pr_url(url: str) -> PrRef | None:
    match = _PR_URL.match(url.strip())
    if match is None:
        return None
    return PrRef(match["owner"], match["repo"], int(match["number"]))


class GhPrStates:
    """Reads PR states through `gh`, using the account configured for the PR's owner."""

    def __init__(self, accounts: dict[str, str], run: Runner = run_command):
        self._accounts = {owner.lower(): name for owner, name in accounts.items()}
        self._run = run
        self._tokens: dict[str, str] = {}

    def state(self, url: str) -> PrState:
        ref = parse_pr_url(url)
        if ref is None:
            raise PrFetchError(f"not a GitHub PR link: {url}")
        env: dict[str, str] = {}
        account = self._accounts.get(ref.owner.lower())
        if account is not None:
            env["GH_TOKEN"] = self._token(account)
        code, stdout, stderr = self._call(
            ["gh", "pr", "view", url, "--json", "state"], env
        )
        if code != 0:
            raise PrFetchError(stderr.strip() or f"gh exited with {code}")
        try:
            state = json.loads(stdout)["state"]
        except (ValueError, KeyError, TypeError) as error:
            raise PrFetchError(
                _with_detail(f"unreadable gh output ({error})", stderr)
            ) from error
        if state not in get_args(PrState):
            raise PrFetchError(_with_detail(f"unexpected PR state {state!r}", stderr))
        return state

    def _token(self, account: str) -> str:
        if account not in self._tokens:
            code, stdout, stderr = self._call(
                ["gh", "auth", "token", "--user", account], {}
            )
            if code != 0 or not stdout.strip():
                raise PrFetchError(
                    stderr.strip() or f"no token for gh account {account!r}"
                )
            self._tokens[account] = stdout.strip()
        return self._tokens[account]

    def _call(self, argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
        try:
            return self._run(argv, env, GH_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise PrFetchError(
                f"gh timed out after {GH_TIMEOUT_SECONDS} seconds"
            ) from error
        except OSError as error:
            raise PrFetchError(f"cannot run {argv[0]}: {error}") from error


def _with_detail(message: str, stderr: str) -> str:
    detail = " ".join(stderr.split())
    return f"{message}: {detail}" if detail else message
