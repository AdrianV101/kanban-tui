"""Find the folder a Claude Code session on a vault task starts in."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from kanban_tui.backends.vault.notes import split_frontmatter

GIT_TIMEOUT_SECONDS = 2


class SessionFolderKind(StrEnum):
    LINKED = "linked"
    NOT_HERE = "not_here"
    SEVERAL = "several"
    NO_LINK = "no_link"
    NO_PROJECT = "no_project"


@dataclass(frozen=True)
class SessionFolder:
    """Where a session on a task can start.

    - `LINKED`: one checkout matches the project's `repos:`; it is `folder`.
    - `NOT_HERE`: the project has `repos:` but no checkout under `root` matches.
    - `SEVERAL`: two or more checkouts match; they are `matches`.
    - `NO_LINK`: the project folder exists but lists no `repos:`.
    - `NO_PROJECT`: the task has no project folder under `01-Projects/`.

    `root` is `checkouts_root` as configured, unexpanded, for messages.
    """

    kind: SessionFolderKind
    project: str | None
    root: str
    folder: Path | None = None
    remotes: tuple[str, ...] = ()
    matches: tuple[Path, ...] = ()


def normalize_remote(url: str) -> str:
    """A git remote as a comparable key, e.g. `github.com/owner/repo`.

    Follows vault-pkm's `normalizeRemote`, so SSH, HTTPS and scp forms of one
    remote give the same key. Empty input gives "".
    """
    rest = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url.strip(), flags=re.IGNORECASE)
    slash = rest.find("/")
    authority_end = len(rest) if slash == -1 else slash
    at = rest.rfind("@", 0, authority_end)
    if at != -1:
        rest = rest[at + 1 :]
    rest = re.sub(r"^([^/:]+):\d+(?=/|$)", r"\1", rest)
    rest = re.sub(r"^([^/:]+):", r"\1/", rest)
    rest = re.sub(r"/+$", "", rest)
    rest = re.sub(r"\.git$", "", rest, flags=re.IGNORECASE)
    return re.sub(r"/+$", "", rest).lower()


def read_repos(index_path: Path) -> tuple[str, ...]:
    """The normalised `repos:` entries in a project's `_index.md` frontmatter.

    A missing file, missing frontmatter, malformed YAML or no `repos:` key
    gives `()`. A single string counts as one entry.
    """
    try:
        parts = split_frontmatter(index_path.read_text(encoding="utf-8"))
        frontmatter = yaml.safe_load(parts[0]) if parts else None
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return ()
    repos = frontmatter.get("repos") if isinstance(frontmatter, dict) else None
    if isinstance(repos, str):
        repos = [repos]
    if not isinstance(repos, list):
        return ()
    keys = (normalize_remote(repo) for repo in repos if isinstance(repo, str))
    return tuple(key for key in keys if key)


def find_checkouts(root: Path, remotes: Iterable[str]) -> list[Path]:
    """Main git checkouts directly under `root` with a remote in `remotes`.

    `remotes` are normalised keys. Any remote of a checkout can match.
    Linked worktrees, nested repos and checkouts whose git lookup fails or
    times out are skipped. `~` in `root` is expanded. Sorted; `[]` when
    `root` does not exist.
    """
    wanted = set(remotes)
    try:
        children = list(root.expanduser().iterdir())
    except (OSError, RuntimeError):
        return []
    return sorted(
        child
        for child in children
        if is_main_checkout(child) and wanted & checkout_remotes(child)
    )


def is_main_checkout(folder: Path) -> bool:
    """A folder whose `.git` is a directory, so not a linked worktree."""
    try:
        return (folder / ".git").is_dir()
    except OSError:
        return False


def checkout_remotes(checkout: Path) -> set[str]:
    """The normalised remotes in a main checkout's `.git/config`.

    A git lookup that fails or times out gives an empty set.
    """
    try:
        result = subprocess.run(
            ["git", "config", "--file", (checkout / ".git" / "config").as_posix()]
            + ["--get-regexp", r"^remote\..*\.url$"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    return {
        normalize_remote(line.split(maxsplit=1)[1])
        for line in result.stdout.splitlines()
        if len(line.split(maxsplit=1)) == 2
    }
