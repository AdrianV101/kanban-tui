from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from kanban_tui.backends.base import Backend
from kanban_tui.backends.vault.notes import (
    NoteReadError,
    TaskNote,
    note_filename,
    read_task_note,
    render_new_task,
    with_status,
)
from kanban_tui.classes.board import Board
from kanban_tui.classes.category import Category
from kanban_tui.classes.column import Column
from kanban_tui.classes.task import Task
from kanban_tui.config import TaskAppendModes, VaultBackendSettings

STATUS_COLUMNS: dict[str, int] = {
    "proposed": 1,
    "pending": 2,
    "active": 3,
    "in-review": 4,
    "done": 5,
    "cancelled": 6,
}
COLUMN_NAMES: dict[int, str] = {
    1: "Proposed",
    2: "Ready",
    3: "Doing",
    4: "In Review",
    5: "Done",
    6: "Archive",
}
FALLBACK_COLUMN = STATUS_COLUMNS["proposed"]
ARCHIVE_COLUMN = STATUS_COLUMNS["cancelled"]
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
CATEGORY_PALETTE = [
    "#4C9AFF",
    "#36B37E",
    "#FF8B00",
    "#6554C0",
    "#FF5630",
    "#00B8D9",
    "#C9B037",
    "#8777D9",
]
BOARD_ID = 1
BOARD_NAME = "Vault"
TEMPLATE_PATH = "05-Templates/task.md"
INBOX_FOLDER = "00-Inbox"


class VaultWriteError(Exception):
    """A board write was refused; the message says why."""


@dataclass
class VaultBackend(Backend):
    """Shows an Obsidian vault's task notes as one board."""

    settings: VaultBackendSettings

    def __post_init__(self):
        self._vault_root = Path(self.settings.vault_path).expanduser()
        self._task_ids: dict[str, int] = {}
        self._category_ids: dict[str, int] = {}
        self._category_colors: dict[str, str] = {}
        self._category_folders: dict[str, str] = {}
        self._tasks: list[Task] = []
        self._warnings: list[str] = []
        self._has_scanned = False

    # === Board Management ===

    def get_boards(self) -> list[Board]:
        try:
            created = datetime.fromtimestamp(self._vault_root.stat().st_ctime)
        except OSError:
            created = datetime.now()
        return [
            Board(
                board_id=BOARD_ID,
                name=BOARD_NAME,
                icon="🗃️",
                creation_date=created,
                reset_column=STATUS_COLUMNS["pending"],
                start_column=STATUS_COLUMNS["active"],
                finish_column=STATUS_COLUMNS["done"],
            )
        ]

    @property
    def active_board(self) -> Board:
        return self.get_boards()[0]

    # === Column Management ===

    def get_columns(self, board_id: int | None = None) -> list[Column]:
        return [
            Column(
                column_id=column_id,
                name=name,
                visible=column_id != ARCHIVE_COLUMN,
                position=column_id - 1,
                board_id=BOARD_ID,
            )
            for column_id, name in COLUMN_NAMES.items()
        ]

    def get_column_by_id(self, column_id: int) -> Column | None:
        for column in self.get_columns():
            if column.column_id == column_id:
                return column
        return None

    # === Scanning ===

    def _find_note_paths(self, warnings: list[str]) -> list[Path]:
        if not self.settings.vault_path:
            warnings.append("vault_path is not set")
            return []
        if not self._vault_root.is_dir():
            warnings.append(f"vault_path {self._vault_root} is not a directory")
            return []
        found: dict[Path, None] = {}
        for pattern in self.settings.task_globs:
            for path in sorted(self._vault_root.glob(pattern)):
                if path.is_file():
                    found[path] = None
        if not found:
            globs = ", ".join(self.settings.task_globs)
            warnings.append(f"no notes in {self._vault_root} match {globs}")
        return list(found)

    def _read_category_name(self, note: TaskNote) -> str | None:
        if note.project:
            return note.project
        parts = Path(note.rel_path).parts
        if len(parts) > 2 and parts[0] == "01-Projects":
            return parts[1]
        if parts[0] == "00-Inbox":
            return self.settings.personal_category
        return None

    def _get_category_id(self, name: str, rel_path: str) -> int:
        if name not in self._category_ids:
            self._category_ids[name] = len(self._category_ids) + 1
            self._category_colors[name] = self.settings.project_colors.get(
                name,
                CATEGORY_PALETTE[
                    (self._category_ids[name] - 1) % len(CATEGORY_PALETTE)
                ],
            )
            self._category_folders[name] = Path(rel_path).parent.as_posix()
        return self._category_ids[name]

    def _get_task_id(self, rel_path: str) -> int:
        if rel_path not in self._task_ids:
            self._task_ids[rel_path] = len(self._task_ids) + 1
        return self._task_ids[rel_path]

    def _note_to_task(
        self, note: TaskNote, modified: datetime, warnings: list[str]
    ) -> Task | None:
        for field_name in note.invalid_fields:
            warnings.append(f"{note.rel_path}: cannot read date in '{field_name}'")

        status = note.status
        column = STATUS_COLUMNS.get(status or "", FALLBACK_COLUMN)
        metadata: dict[str, Any] = {"note_path": note.rel_path, "status": status}
        if status not in STATUS_COLUMNS:
            metadata["unknown_status"] = status

        finish_date = None
        if column == STATUS_COLUMNS["done"]:
            finished = note.finished or modified.date()
            if date.today() - finished > timedelta(
                days=self.settings.done_visible_days
            ):
                return None
            finish_date = datetime.combine(finished, time())

        category_name = self._read_category_name(note)
        category = (
            self._get_category_id(category_name, note.rel_path)
            if category_name
            else None
        )
        return Task(
            task_id=self._get_task_id(note.rel_path),
            title=note.title,
            description=note.description,
            column=column,
            creation_date=(
                datetime.combine(note.created, time()) if note.created else modified
            ),
            finish_date=finish_date,
            due_date=datetime.combine(note.due, time()) if note.due else None,
            category=category,
            metadata=metadata,
        )

    def _scan(self) -> None:
        warnings: list[str] = []
        entries: list[tuple[Task, TaskNote]] = []
        for path in self._find_note_paths(warnings):
            try:
                note = read_task_note(path, self._vault_root)
                if note is None:
                    continue
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except (NoteReadError, OSError) as error:
                warnings.append(str(error))
                continue
            task = self._note_to_task(note, modified, warnings)
            if task:
                entries.append((task, note))

        entries.sort(key=lambda entry: self._order_key(*entry))
        positions: dict[int, int] = {}
        for task, _ in entries:
            task.position = positions.get(task.column, 0)
            positions[task.column] = task.position + 1

        self._tasks = [task for task, _ in entries]
        self._warnings = warnings
        self._has_scanned = True

    @staticmethod
    def _order_key(task: Task, note: TaskNote) -> tuple[int, int, date, date, str]:
        rank = PRIORITY_RANK.get(note.priority or "", len(PRIORITY_RANK))
        return (
            task.column,
            rank,
            task.due_date.date() if task.due_date else date.max,
            task.creation_date.date(),
            note.rel_path,
        )

    # === Task Management ===

    def get_tasks_on_active_board(self) -> list[Task]:
        return self.get_tasks_by_board(BOARD_ID)

    def get_tasks_by_board(self, board_id: int) -> list[Task]:
        self._scan()
        return list(self._tasks)

    def _scanned_tasks(self) -> list[Task]:
        if not self._has_scanned:
            self._scan()
        return self._tasks

    def get_task_by_id(self, task_id: int) -> Task | None:
        for task in self._scanned_tasks():
            if task.task_id == task_id:
                return task
        return None

    def get_tasks_by_ids(self, task_ids: list[int]) -> list[Task]:
        return [task for task in self._scanned_tasks() if task.task_id in task_ids]

    def create_new_task(
        self,
        title: str,
        description: str,
        column: int,
        category: int | None = None,
        due_date: datetime | str | None = None,
    ) -> Task:
        status = next(
            (name for name, number in STATUS_COLUMNS.items() if number == column),
            None,
        )
        if status is None:
            raise VaultWriteError(f"unknown column {column}")
        due = self._read_due_date(due_date)
        project, folder = self._resolve_destination(category)

        try:
            template = (self._vault_root / TEMPLATE_PATH).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise VaultWriteError(
                f"cannot read template {TEMPLATE_PATH} ({error})"
            ) from error
        try:
            content = render_new_task(
                template, title, status, project, due, description, date.today()
            )
        except ValueError as error:
            raise VaultWriteError(f"{TEMPLATE_PATH}: {error}") from error

        rel_path = self._write_new_note(folder, note_filename(title), content)
        self._scan()
        task = self.get_task_by_id(self._get_task_id(rel_path))
        if task is None:
            raise VaultWriteError(f"{rel_path}: written but not shown on the board")
        return task

    @staticmethod
    def _read_due_date(due_date: datetime | str | None) -> date | None:
        if due_date is None or due_date == "":
            return None
        if isinstance(due_date, datetime):
            return due_date.date()
        try:
            return datetime.fromisoformat(due_date).date()
        except ValueError as error:
            raise VaultWriteError(f"cannot read due date {due_date!r}") from error

    def _resolve_destination(self, category: int | None) -> tuple[str | None, str]:
        personal = self.settings.personal_category
        if category is None:
            return None, INBOX_FOLDER
        self._scanned_tasks()
        name = next(
            (name for name, number in self._category_ids.items() if number == category),
            None,
        )
        if name is None:
            raise VaultWriteError(f"unknown category {category}")
        if name == personal:
            return None, INBOX_FOLDER
        folder = self._category_folders.get(name)
        if folder is None:
            raise VaultWriteError(f"no known tasks folder for project {name!r}")
        return name, folder

    def _write_new_note(self, folder: str, filename: str, content: str) -> str:
        directory = self._vault_root / folder
        stem = Path(filename).stem
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for attempt in range(1, 1000):
                name = filename if attempt == 1 else f"{stem}-{attempt}.md"
                path = directory / name
                try:
                    with open(path, "x", encoding="utf-8", newline="") as handle:
                        try:
                            handle.write(content)
                        except BaseException:
                            handle.close()
                            path.unlink(missing_ok=True)
                            raise
                except FileExistsError:
                    continue
                return path.relative_to(self._vault_root).as_posix()
        except OSError as error:
            raise VaultWriteError(f"cannot write note in {folder} ({error})") from error
        raise VaultWriteError(f"no free file name for {filename} in {folder}")

    def _refuse(self, rel_path: str, reason: str) -> dict[str, Any]:
        return {"success": False, "message": f"{rel_path}: {reason}"}

    def update_task_status(
        self,
        new_task: Task,
        target_position: int | None = None,
        append_mode: TaskAppendModes | None = None,
    ) -> Task | dict[str, Any]:
        rel_path = new_task.metadata["note_path"]
        scanned_status = new_task.metadata["status"]
        target_status = next(
            status
            for status, column in STATUS_COLUMNS.items()
            if column == new_task.column
        )
        path = self._vault_root / rel_path
        try:
            current = read_task_note(path, self._vault_root)
            raw = path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            return self._refuse(rel_path, "note no longer exists, reload the board")
        except (NoteReadError, OSError, UnicodeDecodeError) as error:
            return self._refuse(rel_path, f"cannot read note ({error})")
        if current is None:
            return self._refuse(rel_path, "note is no longer a task note")
        if current.status != scanned_status:
            return self._refuse(
                rel_path,
                f"status changed on disk to {current.status!r}, reload the board",
            )

        finished = date.today() if target_status == "done" else None
        try:
            updated = with_status(raw, target_status, finished)
            self._replace_file(path, updated)
        except (ValueError, OSError) as error:
            return self._refuse(rel_path, f"cannot write note ({error})")

        new_task.metadata["status"] = target_status
        self._scan()
        return self.get_task_by_id(new_task.task_id) or new_task

    def delete_task(self, task_id: int) -> None:
        task = self.get_task_by_id(task_id)
        if task is None:
            raise VaultWriteError("note is not on the board, reload the board")
        archived = task.model_copy(
            update={"column": ARCHIVE_COLUMN, "metadata": dict(task.metadata)}
        )
        result = self.update_task_status(archived)
        if isinstance(result, dict):
            raise VaultWriteError(result["message"])

    def note_url(self, task: Task) -> str:
        rel_path = Path(task.metadata["note_path"]).with_suffix("").as_posix()
        vault = quote(self._vault_root.name, safe="")
        return f"obsidian://open?vault={vault}&file={quote(rel_path, safe='')}"

    @staticmethod
    def _replace_file(path: Path, content: str) -> None:
        handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as temp_file:
                temp_file.write(content.encode("utf-8"))
            os.chmod(temp_name, path.stat().st_mode)
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def get_warnings(self) -> list[str]:
        return list(self._warnings)

    # === Categories ===

    def get_all_categories(self) -> list[Category]:
        return [
            Category(
                category_id=category_id,
                name=name,
                color=self._category_colors[name],
            )
            for name, category_id in self._category_ids.items()
        ]

    def get_category_by_id(self, category_id: int) -> Category:
        for category in self.get_all_categories():
            if category.category_id == category_id:
                return category
        raise KeyError(f"No category with id {category_id}")

    def get_board_infos(self):
        board = self.active_board
        return [
            {
                "board_id": board.board_id,
                "name": board.name,
                "icon": board.icon,
                "amount_tasks": len(self.get_tasks_by_board(board.board_id)),
                "amount_columns": len(self.get_columns()),
                "next_due": None,
            }
        ]

    # === Not Supported Yet ===

    def create_new_board(
        self,
        name: str,
        icon: str | None = None,
        column_dict: dict[str, bool] | None = None,
    ) -> Board:
        raise NotImplementedError("Vault backend has a single fixed board.")

    def delete_board(self, board_id: int):
        raise NotImplementedError("Vault backend has a single fixed board.")

    def update_board(self, board_id: int, name: str, icon: str):
        raise NotImplementedError("Vault backend has a single fixed board.")

    def create_new_category(self, name: str, color: str) -> Category:
        raise NotImplementedError("Vault backend derives categories from projects.")

    def update_category(self, category_id: int, name: str, color: str) -> Category:
        raise NotImplementedError("Vault backend derives categories from projects.")

    def delete_category(self, category_id: int):
        raise NotImplementedError("Vault backend derives categories from projects.")

    def update_column_visibility(self, column_id: int, visible: bool):
        raise NotImplementedError("Vault backend has fixed columns.")

    def update_column_name(self, column_id: int, new_name: str):
        raise NotImplementedError("Vault backend has fixed columns.")

    def create_task_dependency(self, task_id: int, depends_on_task_id: int) -> int:
        raise NotImplementedError("Vault backend does not support dependencies.")

    def delete_task_dependency(self, task_id: int, depends_on_task_id: int) -> int:
        raise NotImplementedError("Vault backend does not support dependencies.")

    def would_create_dependency_cycle(
        self, task_id: int, depends_on_task_id: int
    ) -> bool:
        return False
