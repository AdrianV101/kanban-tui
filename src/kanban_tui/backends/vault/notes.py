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
