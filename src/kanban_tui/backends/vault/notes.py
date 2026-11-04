from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


class NoteReadError(Exception): ...


@dataclass
class TaskNote:
    rel_path: str
    text: str
    frontmatter: dict[str, Any]
    title: str
    description: str
    status: str | None
    project: str | None
    priority: str | None
    due: date | None
    created: date | None
    finished: date | None
    invalid_fields: list[str] = field(default_factory=list)


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split into the YAML block between the first two `---` lines and the body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def read_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def read_description(body: str) -> str:
    match = re.search(
        r"^## Description[ \t]*\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL
    )
    return match.group(1).strip() if match else ""


def read_task_note(path: Path, vault_root: Path) -> TaskNote | None:
    """Parse a note into a TaskNote, or None when it is not a task note.

    Raises:
        NoteReadError: the bytes are unreadable or the frontmatter is malformed.
    """
    rel_path = path.relative_to(vault_root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise NoteReadError(f"{rel_path}: cannot read note ({error})") from error

    parts = split_frontmatter(text)
    if parts is None:
        return None
    block, body = parts
    try:
        frontmatter = yaml.safe_load(block)
    except yaml.YAMLError as error:
        raise NoteReadError(f"{rel_path}: malformed frontmatter") from error
    if not isinstance(frontmatter, dict) or frontmatter.get("type") != "task":
        return None

    invalid_fields: list[str] = []
    dates: dict[str, date | None] = {}
    for name in ("due", "created", "finished"):
        try:
            dates[name] = parse_date(frontmatter.get(name))
        except ValueError:
            dates[name] = None
            invalid_fields.append(name)

    raw_status = frontmatter.get("status")
    raw_project = frontmatter.get("project")
    raw_priority = frontmatter.get("priority")
    return TaskNote(
        rel_path=rel_path,
        text=text,
        frontmatter=frontmatter,
        title=read_title(body, path.stem),
        description=read_description(body),
        status=None if raw_status is None else str(raw_status),
        project=None if raw_project is None else str(raw_project),
        priority=None if raw_priority is None else str(raw_priority).lower(),
        due=dates["due"],
        created=dates["created"],
        finished=dates["finished"],
        invalid_fields=invalid_fields,
    )


STATUS_LINE = re.compile(r"^(status:[ \t]*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]*)(.*)$")
FINISHED_LINE = re.compile(r"^(finished:[ \t]*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]*)(.*)$")


def with_status(text: str, status: str, finished: date | None) -> str:
    """Return text with the frontmatter `status` value replaced.

    Quotes, trailing comments, line endings and every other byte are kept. When
    `finished` is given, its line is replaced or added as the last frontmatter line.

    Raises:
        ValueError: the text has no frontmatter or no `status` line in it.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("note has no frontmatter")
    closing = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing is None:
        raise ValueError("note has no frontmatter")

    status_index = finished_index = None
    for index in range(1, closing):
        content = lines[index].rstrip("\r\n")
        if status_index is None and STATUS_LINE.match(content):
            status_index = index
        elif finished_index is None and FINISHED_LINE.match(content):
            finished_index = index
    if status_index is None:
        raise ValueError("note has no status line")

    def replace_value(index: int, pattern: re.Pattern[str], value: str) -> None:
        line = lines[index]
        content = line.rstrip("\r\n")
        match = pattern.match(content)
        assert match is not None
        prefix, old_value, comment = match.groups()
        if not old_value:
            prefix = prefix if prefix[-1] in " \t" else prefix + " "
            comment = f" {comment}" if comment else ""
        quote = old_value[:1] if old_value[:1] in "\"'" else ""
        lines[index] = f"{prefix}{quote}{value}{quote}{comment}{line[len(content) :]}"

    replace_value(status_index, STATUS_LINE, status)
    if finished is not None:
        if finished_index is not None:
            replace_value(finished_index, FINISHED_LINE, finished.isoformat())
        else:
            previous = lines[closing - 1]
            ending = previous[len(previous.rstrip("\r\n")) :]
            lines.insert(closing, f"finished: {finished.isoformat()}{ending}")
    return "".join(lines)
