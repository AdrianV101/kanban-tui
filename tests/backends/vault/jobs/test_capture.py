from pathlib import Path

import pytest

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.backends.vault.jobs.capture import (
    CAPTURE_PATH,
    CaptureItem,
    CaptureWriteError,
    read_capture_items,
    remove_capture_lines,
)


def write_capture(vault: Path, content: bytes) -> Path:
    path = vault / CAPTURE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.mark.parametrize(
    ("line", "text"),
    [
        ("- call the plumber", "call the plumber"),
        ("* call the plumber", "call the plumber"),
        ("- [ ] call the plumber", "call the plumber"),
        ("call the plumber", "call the plumber"),
        ("   -   call the plumber  ", "call the plumber"),
        ("#idea buy milk", "#idea buy milk"),
    ],
)
def test_read_strips_bullets_and_whitespace(tmp_path: Path, line: str, text: str):
    write_capture(tmp_path, f"{line}\n".encode())
    assert read_capture_items(tmp_path) == [CaptureItem("c1", line, text)]


@pytest.mark.parametrize(
    "line", ["# Capture", "## Inbox", "#", "  ### x", "###### six"]
)
def test_read_skips_markdown_headings(tmp_path: Path, line: str):
    write_capture(tmp_path, f"{line}\n- real\n".encode())
    assert [i.text for i in read_capture_items(tmp_path)] == ["real"]


def test_read_skips_blank_lines_and_numbers_in_file_order(tmp_path: Path):
    write_capture(tmp_path, b"- one\n\n   \r\n* two\r\nthree")
    items = read_capture_items(tmp_path)
    assert [(i.id, i.line, i.text) for i in items] == [
        ("c1", "- one", "one"),
        ("c2", "* two", "two"),
        ("c3", "three", "three"),
    ]


def test_read_missing_file_gives_empty_list(tmp_path: Path):
    assert read_capture_items(tmp_path) == []


def test_remove_drops_given_lines_and_keeps_late_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = write_capture(tmp_path, b"- a\n- b\n- c\n")
    original = VaultBackend._replace_file
    calls = []

    def replace_after_phone_append(target, content, read_stat):
        calls.append(content)
        if len(calls) == 1:
            with open(target, "ab") as handle:
                handle.write(b"- late\n")
        original(target, content, read_stat)

    monkeypatch.setattr(
        VaultBackend, "_replace_file", staticmethod(replace_after_phone_append)
    )
    remove_capture_lines(tmp_path, ["- a", "- c"])
    assert path.read_bytes() == b"- b\n- late\n"
    assert len(calls) == 2


def test_remove_keeps_crlf_and_every_other_byte(tmp_path: Path):
    path = write_capture(tmp_path, "- a\r\n\r\n- é b\r\n- a\r\nlast".encode())
    remove_capture_lines(tmp_path, ["- a", "last"])
    assert path.read_bytes() == "\r\n- é b\r\n- a\r\n".encode()


def test_remove_missing_file_is_a_no_op(tmp_path: Path):
    remove_capture_lines(tmp_path, ["- a"])
    assert not (tmp_path / CAPTURE_PATH).exists()


def test_remove_gives_up_after_three_attempts_leaving_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = write_capture(tmp_path, b"- a\n")
    original = VaultBackend._replace_file
    attempts = []

    def always_changing(target, content, read_stat):
        attempts.append(1)
        with open(target, "ab") as handle:
            handle.write(b"- x\n")
        original(target, content, read_stat)

    monkeypatch.setattr(VaultBackend, "_replace_file", staticmethod(always_changing))
    with pytest.raises(CaptureWriteError):
        remove_capture_lines(tmp_path, ["- a"])
    assert len(attempts) == 3
    assert path.read_bytes() == b"- a\n" + b"- x\n" * 3
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("line", ["-", "- ", "* ", "*", "- [ ]", "- [x] ", "  -  "])
def test_read_skips_bullet_only_lines(tmp_path: Path, line: str):
    write_capture(tmp_path, f"{line}\n- real\n".encode())
    assert [i.text for i in read_capture_items(tmp_path)] == ["real"]


def test_read_skips_frontmatter_and_headings(tmp_path: Path):
    write_capture(
        tmp_path, b"---\ntags: [capture]\n---\n# Capture\n- one\n  ## sub\ntwo\n"
    )
    assert [(i.id, i.text) for i in read_capture_items(tmp_path)] == [
        ("c1", "one"),
        ("c2", "two"),
    ]


def test_remove_leaves_frontmatter_and_headings_byte_identical(tmp_path: Path):
    path = write_capture(
        tmp_path, b"---\ntags: [capture]\n---\n# Capture\n- one\n- two\n"
    )
    items = read_capture_items(tmp_path)
    remove_capture_lines(tmp_path, [i.line for i in items])
    assert path.read_bytes() == b"---\ntags: [capture]\n---\n# Capture\n"
