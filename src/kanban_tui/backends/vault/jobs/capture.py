from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from kanban_tui.backends.vault.backend import VaultBackend, VaultWriteError

CAPTURE_PATH = "00-Inbox/Capture.md"
MAX_ATTEMPTS = 3
_LINES = re.compile(r"[^\n]*\n|[^\n]+")
_HEADING = re.compile(r"^ *#{1,6}(?: |$)")
_BULLET = re.compile(r"^(?:[-*](?:\s+(?:\[.\]\s*)?|$))?")


class CaptureWriteError(Exception):
    """Capture.md kept changing while lines were being removed."""


@dataclass(frozen=True)
class CaptureItem:
    id: str
    line: str
    text: str


def _raw(line_with_ending: str) -> str:
    return line_with_ending.removesuffix("\n").removesuffix("\r")


def _protected_lines(entries: list[str]) -> set[int]:
    """Indexes of the frontmatter block and heading lines, which are never captures."""
    protected = {i for i, e in enumerate(entries) if _HEADING.match(_raw(e))}
    if entries and _raw(entries[0]).rstrip() == "---":
        for index in range(1, len(entries)):
            if _raw(entries[index]).rstrip() == "---":
                protected.update(range(index + 1))
                break
    return protected


def read_capture_items(vault: Path) -> list[CaptureItem]:
    path = vault / CAPTURE_PATH
    try:
        content = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return []
    items: list[CaptureItem] = []
    entries = _LINES.findall(content)
    protected = _protected_lines(entries)
    for index, entry in enumerate(entries):
        if index in protected:
            continue
        line = _raw(entry)
        text = _BULLET.sub("", line.strip(), count=1).strip()
        if text:
            items.append(CaptureItem(f"c{len(items) + 1}", line, text))
    return items


def remove_capture_lines(vault: Path, lines: list[str]) -> None:
    path = vault / CAPTURE_PATH
    for _ in range(MAX_ATTEMPTS):
        try:
            read_stat = path.stat()
            content = path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            return
        entries = _LINES.findall(content)
        protected = _protected_lines(entries)
        dropped: set[int] = set()
        for line in lines:
            for index, entry in enumerate(entries):
                if (
                    index not in protected
                    and index not in dropped
                    and _raw(entry) == line
                ):
                    dropped.add(index)
                    break
        updated = "".join(e for i, e in enumerate(entries) if i not in dropped)
        if updated == content:
            return
        try:
            VaultBackend._replace_file(path, updated, read_stat)
        except VaultWriteError:
            continue
        return
    raise CaptureWriteError(
        f"{CAPTURE_PATH} changed on every one of {MAX_ATTEMPTS} attempts"
    )
