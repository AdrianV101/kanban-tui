from __future__ import annotations

import json
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
    board: str | None
    project: str | None
    priority: str | None
    prs: list[str]
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


def read_prs(value: Any) -> list[str] | None:
    """The PR URLs in a `prs` value, or None when the value is not a string or list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None


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
    return parse_task_note(text, rel_path, path.stem)


def parse_task_note(text: str, rel_path: str, fallback_title: str) -> TaskNote | None:
    """Parse note text into a TaskNote, or None when it is not a task note.

    Line endings are normalised to `\\n` in the result, as a text-mode read does.

    Raises:
        NoteReadError: the frontmatter is malformed.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
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
    raw_board = frontmatter.get("board")
    raw_project = frontmatter.get("project")
    raw_priority = frontmatter.get("priority")
    prs = read_prs(frontmatter.get("prs"))
    if prs is None:
        prs = []
        invalid_fields.append("prs")
    return TaskNote(
        rel_path=rel_path,
        text=text,
        frontmatter=frontmatter,
        title=read_title(body, fallback_title),
        description=read_description(body),
        status=None if raw_status is None else str(raw_status),
        board=None if raw_board is None else str(raw_board),
        project=None if raw_project is None else str(raw_project),
        priority=None if raw_priority is None else str(raw_priority).lower(),
        prs=prs,
        due=dates["due"],
        created=dates["created"],
        finished=dates["finished"],
        invalid_fields=invalid_fields,
    )


def field_line(name: str) -> re.Pattern[str]:
    return re.compile(rf"^({name}:[ \t]*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]*)(.*)$")


STATUS_LINE = field_line("status")
BOARD_LINE = field_line("board")
FINISHED_LINE = field_line("finished")


def with_card_fields(
    text: str, status: str, board: str | None, finished: date | None
) -> str:
    """Return text with the frontmatter `status` value replaced, and optionally `board`.

    Quotes, trailing comments, line endings and every other byte are kept. A `board`
    that is not None is replaced, or added as the last frontmatter line; None leaves
    any `board` line alone. `finished` is handled the same way.

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

    found: dict[str, int] = {}
    for index in range(1, closing):
        content = lines[index].rstrip("\r\n")
        for name, pattern in (
            ("status", STATUS_LINE),
            ("board", BOARD_LINE),
            ("finished", FINISHED_LINE),
        ):
            if name not in found and pattern.match(content):
                found[name] = index
                break
    if "status" not in found:
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

    replace_value(found["status"], STATUS_LINE, status)
    for name, pattern, value in (
        ("board", BOARD_LINE, board),
        ("finished", FINISHED_LINE, finished.isoformat() if finished else None),
    ):
        if value is None:
            continue
        if name in found:
            replace_value(found[name], pattern, value)
        else:
            previous = lines[closing - 1]
            ending = previous[len(previous.rstrip("\r\n")) :]
            lines.insert(closing, f"{name}: {value}{ending}")
            closing += 1
    return "".join(lines)


def with_appended_line(text: str, line: str) -> str:
    """Return text with `line` as its last line.

    A line break is added first when the text does not end with one. The note's own
    line ending is used, and every existing byte is kept.
    """
    ending = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith(("\n", "\r")):
        text += ending
    return f"{text}{line}{ending}"


def note_filename(title: str) -> str:
    """Kebab-case file name for a title; `task.md` when nothing usable is left."""
    slug = re.sub(r"[\W_]+", "-", title.lower()).strip("-")[:100].strip("-")
    return f"{slug or 'task'}.md"


TEMPLATE_DATE = re.compile(r"<%\s*tp\.date\.now\(\s*[\"']YYYY-MM-DD[\"']\s*\)\s*%>")
TEMPLATE_TITLE = re.compile(r"<%\s*tp\.file\.title\s*%>")
SAFE_YAML_SCALAR = re.compile(r"^[\w][\w .\-/]*$")


def render_new_task(
    template_text: str,
    title: str,
    status: str,
    board: str | None,
    project: str | None,
    due: date | None,
    description: str,
    today: date,
    source: str | None = None,
) -> str:
    """Fill the vault's task template for a new note.

    Template placeholders are substituted; `status` is always set, `board`, `project`,
    `due` and `source` only when given. A non-empty `description` goes under `## Description`.

    Raises:
        ValueError: the template has no frontmatter.
    """
    text = TEMPLATE_DATE.sub(today.isoformat(), template_text)
    text = TEMPLATE_TITLE.sub(lambda _: title, text)

    lines = text.splitlines(keepends=True)
    closing = next(
        (i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if not lines or lines[0].strip() != "---" or closing is None:
        raise ValueError("template has no frontmatter")

    fields: dict[str, str] = {"status": status}
    if board is not None:
        fields["board"] = board
    if project is not None:
        fields["project"] = (
            project if SAFE_YAML_SCALAR.match(project) else json.dumps(project)
        )
    if source is not None:
        fields["source"] = (
            source if SAFE_YAML_SCALAR.match(source) else json.dumps(source)
        )
    if due is not None:
        fields["due"] = due.isoformat()
    for key, value in fields.items():
        pattern = re.compile(rf"^{key}:")
        index = next(
            (i for i in range(1, closing) if pattern.match(lines[i])),
            None,
        )
        if index is None:
            lines.insert(closing, f"{key}: {value}\n")
            closing += 1
            continue
        ending = lines[index][len(lines[index].rstrip("\r\n")) :]
        lines[index] = f"{key}: {value}{ending}"
    text = "".join(lines)

    if description.strip():
        section = f"## Description\n\n{description.strip()}\n\n"
        text, count = re.subn(
            r"^## Description[ \t]*\n.*?(?=^## |\Z)",
            lambda _: section,
            text,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )
        if count == 0:
            text = f"{text.rstrip()}\n\n{section.rstrip()}\n"
    return text
