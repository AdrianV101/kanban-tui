"""Find the folder a Claude Code session on a vault task starts in."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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
    raise NotImplementedError


def read_repos(index_path: Path) -> tuple[str, ...]:
    """The normalised `repos:` entries in a project's `_index.md` frontmatter.

    A missing file, missing frontmatter, malformed YAML or no `repos:` key
    gives `()`. A single string counts as one entry.
    """
    raise NotImplementedError


def find_checkouts(root: Path, remotes: Iterable[str]) -> list[Path]:
    """Main git checkouts directly under `root` with a remote in `remotes`.

    `remotes` are normalised keys. Any remote of a checkout can match.
    Linked worktrees, nested repos and checkouts whose git lookup fails or
    times out are skipped. `~` in `root` is expanded. Sorted; `[]` when
    `root` does not exist.
    """
    raise NotImplementedError
