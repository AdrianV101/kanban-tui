from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.sessions import (
    SessionFolderKind,
    find_checkouts,
    normalize_remote,
    read_repos,
)
from kanban_tui.classes.task import Task
from kanban_tui.config import VaultBackendSettings
from tests.conftest import make_checkout, write_task_note

KEY = "github.com/owner/repo"
ONE_REMOTE_FORMS = [
    "https://github.com/owner/repo",
    "https://github.com/owner/repo.git",
    "https://github.com/owner/repo/",
    "https://github.com/owner/repo.git/",
    "http://github.com/owner/repo.git",
    "https://user:secret@github.com/owner/repo.git",
    "https://token@github.com/owner/repo",
    "ssh://git@github.com/owner/repo.git",
    "ssh://git@github.com:2222/owner/repo.git",
    "ssh://github.com/owner/repo",
    "git://github.com/owner/repo.git",
    "git+ssh://git@github.com/owner/repo.git",
    "git@github.com:owner/repo.git",
    "github.com:owner/repo",
    "github.com/owner/repo",
    "HTTPS://GitHub.com/Owner/Repo.git",
    "  https://github.com/owner/repo.git\n",
]


@pytest.mark.parametrize("url", ONE_REMOTE_FORMS)
def test_every_form_of_one_remote_gives_the_same_key(url: str):
    assert normalize_remote(url) == KEY


def test_normalising_keeps_extra_segments_and_keeps_repos_apart():
    assert normalize_remote("git@gitlab.com:group/sub/repo.git") == (
        "gitlab.com/group/sub/repo"
    )
    assert normalize_remote("https://gitlab.com:8443/group/sub/repo") == (
        "gitlab.com/group/sub/repo"
    )
    assert normalize_remote("github.com/a/repo") != normalize_remote(
        "github.com/b/repo"
    )
    assert normalize_remote("github.com/a/repo") != normalize_remote(
        "gitlab.com/a/repo"
    )


@pytest.mark.parametrize("url", ["", "   \n"])
def test_empty_input_normalises_to_nothing(url: str):
    assert normalize_remote(url) == ""


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            (
                "---\ntype: project\nrepos:\n  - git@github.com:Owner/Repo.git\n"
                "  - https://gitlab.com/g/other\n---\n# P\n"
            ),
            (KEY, "gitlab.com/g/other"),
        ),
        ("---\nrepos: [github.com/owner/repo]\n---\n", (KEY,)),
        ("---\nrepos: https://github.com/owner/repo\n---\n", (KEY,)),
        ("---\ntype: project\n---\n# P\n", ()),
        ("# P\nrepos: [github.com/owner/repo]\n", ()),
        ("---\nrepos: [github.com/owner/repo\n---\n", ()),
        (None, ()),
    ],
    ids=[
        "block-list",
        "inline-list",
        "single-string",
        "no-repos-key",
        "no-frontmatter",
        "malformed-yaml",
        "missing-file",
    ],
)
def test_read_repos_gives_the_normalised_entries(
    tmp_path: Path, content: str | None, expected: tuple[str, ...]
):
    index = tmp_path / "_index.md"
    if content is not None:
        index.write_text(content, encoding="utf-8")

    assert read_repos(index) == expected


def test_find_checkouts_returns_exactly_the_matching_main_checkouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "root"
    a = make_checkout(root / "a", {"origin": "git@github.com:owner/repo.git"})
    b = make_checkout(
        root / "b",
        {"origin": "https://github.com/me/fork", "upstream": "github.com/owner/repo"},
    )
    subprocess.run(
        ["git", "-C", a.as_posix(), "worktree", "add", "-q", (root / "wt").as_posix()],
        check=True,
    )
    make_checkout(root / "c", {"origin": "https://github.com/someone/else"})
    (root / "plain").mkdir()
    make_checkout(root / "deep" / "inner", {"origin": "github.com/owner/repo"})
    slow = make_checkout(root / "slow", {"origin": "github.com/owner/repo"})
    broken = root / "broken" / ".git"
    broken.mkdir(parents=True)
    (broken / "config").write_text('[remote "origin"\n\turl = x\n', encoding="utf-8")

    real_run = subprocess.run

    def run(argv: list[str], **kwargs: Any) -> Any:
        if any(slow.as_posix() in str(arg) for arg in argv):
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 0)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)

    assert find_checkouts(root, [KEY]) == [a, b]

    monkeypatch.setenv("HOME", tmp_path.as_posix())
    assert find_checkouts(Path("~/root"), [KEY]) == [a, b]


def test_find_checkouts_gives_nothing_for_a_missing_root(tmp_path: Path):
    assert find_checkouts(tmp_path / "nowhere", [KEY]) == []


def make_backend(vault: Path, root: Path) -> VaultBackend:
    return VaultBackend(
        VaultBackendSettings(
            vault_path=vault.as_posix(), checkouts_root=root.as_posix()
        )
    )


def task_at(backend: VaultBackend, rel_path: str) -> Task:
    return next(
        task
        for task in backend.get_tasks_on_active_board()
        if task.metadata["note_path"] == rel_path
    )


def write_index(vault: Path, project: str, repos: list[str] | None) -> None:
    folder = vault / "01-Projects" / project
    folder.mkdir(parents=True, exist_ok=True)
    if repos is None:
        return
    lines = ["---", "type: project"]
    if repos:
        lines += ["repos:"] + [f"  - {repo}" for repo in repos]
    (folder / "_index.md").write_text("\n".join(lines + ["---", ""]), encoding="utf-8")


CASES = {
    "linked": ("01-Projects/Alpha/tasks/t.md", None, [KEY], ["a"]),
    "not-here": ("01-Projects/Alpha/tasks/t.md", None, ["github.com/x/missing"], ["a"]),
    "several": ("01-Projects/Alpha/tasks/t.md", None, [KEY], ["a", "b"]),
    "no-index": ("01-Projects/Alpha/tasks/t.md", None, None, ["a"]),
    "index-without-repos": ("01-Projects/Alpha/tasks/t.md", None, [], ["a"]),
    "inbox-no-project": ("00-Inbox/t.md", None, [KEY], ["a"]),
    "inbox-unknown-project": ("00-Inbox/t.md", "Ghost", [KEY], ["a"]),
    "inbox-linked-project": ("00-Inbox/t.md", "Alpha", [KEY], ["a"]),
}
EXPECTED = {
    "linked": (SessionFolderKind.LINKED, "Alpha", "a", ()),
    "not-here": (SessionFolderKind.NOT_HERE, "Alpha", None, ()),
    "several": (SessionFolderKind.SEVERAL, "Alpha", None, ("a", "b")),
    "no-index": (SessionFolderKind.NO_LINK, "Alpha", None, ()),
    "index-without-repos": (SessionFolderKind.NO_LINK, "Alpha", None, ()),
    "inbox-no-project": (SessionFolderKind.NO_PROJECT, None, None, ()),
    "inbox-unknown-project": (SessionFolderKind.NO_PROJECT, None, None, ()),
    "inbox-linked-project": (SessionFolderKind.LINKED, "Alpha", "a", ()),
}


@pytest.mark.parametrize("case", list(CASES))
def test_session_folder_gives_the_outcome_for_each_kind_of_card(
    test_vault: Path, tmp_path: Path, case: str
):
    note, project_field, repos, checkouts = CASES[case]
    kind, project, folder, matches = EXPECTED[case]
    root = tmp_path / "root"
    for name in checkouts:
        make_checkout(root / name, {"origin": "https://github.com/owner/repo.git"})
    write_index(test_vault, "Alpha", repos)
    write_task_note(test_vault, note, {"project": project_field})
    backend = make_backend(test_vault, root)

    result = backend.session_folder(task_at(backend, note))

    assert result.kind == kind
    assert result.project == project
    assert result.root == root.as_posix()
    assert result.folder == (root / folder if folder else None)
    assert result.matches == tuple(root / name for name in matches)
    if kind in (SessionFolderKind.NOT_HERE, SessionFolderKind.LINKED):
        assert result.remotes == tuple(normalize_remote(repo) for repo in repos or [])
