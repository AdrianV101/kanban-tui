# Kanban-tui Vault Backend Implementation Plan

> **Status:** done (commits `31e8a32`..`1f6edaa`). Its `proposed` and `in-review` status values are superseded by the [board field plan](2026-11-04-board-field.md): the board now keeps vault-pkm's four statuses and adds a `board` field.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** kanban-tui shows the owner's vault task notes as one six-column board, and moving, creating or archiving a card writes the note directly.

**Architecture:** A new `VaultBackend` sits beside the sqlite, jira and claude backends in a fork of kanban-tui. It scans task notes once per refresh, serves lookups from that scan, and writes by editing single frontmatter lines in place. A small `notes` module owns parsing and text edits, so the backend never re-serialises YAML. The UI changes are limited to places that already branch on `backend.mode`.

**Tech Stack:** Python 3.11+, Textual 8, pydantic, PyYAML (new optional extra `vault`), pytest with Textual pilot tests, freezegun, ruff, mypy.

**Spec:** [design](../design.md) . This plan covers build-order part 1 only.

## Global Constraints

- Fork of `Zaloog/kanban-tui` at main `9e371e5` (v0.21.2), as `AdrianV101/kanban-tui`. Clone to `~/Projects/kanban-tui`, work on branch `vault-backend`, `upstream` remote kept.
- Statuses and columns, exactly: `proposed` Proposed (1), `pending` Ready (2), `active` Doing (3), `in-review` In Review (4), `done` Done (5), `cancelled` Archive (6, not visible).
- The board never deletes a note file.
- A board write changes only the `status` line, plus a `finished: YYYY-MM-DD` line when a card enters Done. Every other byte of the note is kept.
- A write must not overwrite a newer version of the note. If the status on disk differs from the status the card was scanned with, the write is refused.
- Every refusal reaches the user as a visible error. Nothing is skipped silently.
- PyYAML ships as the optional extra `vault` (`kanban-tui[vault]`). `types-PyYAML` joins the dev group.
- The sqlite, jira and claude backends keep their behaviour. The existing suite stays green.
- Repo practice: tests in `tests/`, real files in `tmp_path`, Textual pilot tests for UI, `freezegun` for dates, `make test` and `make check` (ruff + mypy) clean.
- Commits carry no AI attribution.
- Using the board on the real vault waits for part 2's first change: vault-pkm's task enum gaining `proposed` and `in-review`. Until then, only run against a copy of the vault.

## Review Focus

These are the inputs the spec implies but doesn't name, ranked by how likely each is to bite. Each one has its test in the owning task.

1. The note's body or other fields change in Obsidian or arrive through Sync between scan and move, but the status doesn't. The move should succeed and keep those changes. (Task 2, test 2.4)
2. Frontmatter written by other tools uses a quoted status, an inline comment, or status as the last frontmatter line. A move must still change only that value. (Task 2, test 2.2)
3. A title contains `/`, `:`, emoji, or only symbols. The filename must be safe, and a symbol-only title falls back to `task`. (Task 3, test 3.2)
4. A project name has a space (`Side Project`). The folder must resolve, and the Obsidian link must be URL-encoded. (Task 3, test 3.1; Task 4, test 4.2)
5. `due` or `created` is invalid or missing. The card still loads without that date, and an invalid value raises a warning. (Task 1, test 1.6)

---

### Task 1: The board reads the vault

**Files:**
- Modify: `src/kanban_tui/config.py`: add `Backends.VAULT = "vault"`, a `VaultBackendSettings` model, and `BackendSettings.vault_settings`.
- Modify: `src/kanban_tui/backends/base.py`: add `get_warnings(self) -> list[str]`, returning `[]` by default.
- Create: `src/kanban_tui/backends/vault/__init__.py` and `src/kanban_tui/backends/vault/notes.py` (parsing only in this task).
- Create: `src/kanban_tui/backends/vault/backend.py` (`VaultBackend`, read side).
- Modify: `src/kanban_tui/app.py`:
  - `get_backend()` gets a `VAULT` case, lazily imported like `CLAUDE`.
  - `update_backend()` gets a `VAULT` case.
  - `action_refresh()` notifies with any `backend.get_warnings()`.
- Modify: `pyproject.toml` (extra `vault = ["pyyaml>=6.0"]`, dev `types-PyYAML`).
- Test: `tests/backends/vault/test_vault_read.py`, `tests/app_tests/test_vault_backend_integration.py`.
- Test fixture: `tests/conftest.py` gains:
  - `test_vault(tmp_path)`, which writes a vault with `05-Templates/task.md` copied from the real vault's template.
  - A `write_task_note(vault, rel_path, frontmatter, body)` helper.
  - `vault_app`, a `KanbanTui` configured with `mode = vault` on that vault.

**Interfaces:**
- Produces:
  - `VaultBackendSettings` fields, with defaults:
    - `vault_path: str = ""`
    - `task_globs: list[str] = ["01-Projects/*/tasks/*.md", "00-Inbox/*.md"]`
    - `done_visible_days: int = 7`
    - `project_colors: dict[str, str] = {}`
    - `personal_category: str = "Personal"`
  - `VaultBackend(settings: VaultBackendSettings)` is a dataclass like `ClaudeBackend`.
  - `STATUS_COLUMNS: dict[str, int]` follows the Global Constraints mapping. `COLUMN_NAMES: dict[int, str]` holds the column names.
  - `notes.read_task_note(path: Path, vault_root: Path) -> TaskNote | None` returns `None` for non-task notes. `TaskNote` holds:
    - `rel_path: str`, `text: str` and `frontmatter: dict[str, Any]`
    - `title: str` and `description: str`
    - `status: str | None` and `project: str | None`
    - `priority: str | None`, `due: date | None`, `created: date | None` and `finished: date | None`
  - Card metadata keys: `note_path` (vault-relative), `status` (as scanned), and `unknown_status` (only when the fallback applied).
  - `VaultBackend` methods:
    - Read methods match `ClaudeBackend`: `get_boards`, `active_board`, `get_columns`, `get_tasks_on_active_board`, `get_tasks_by_board`, `get_task_by_id`, `get_tasks_by_ids`, `get_column_by_id`, `get_all_categories`, `get_category_by_id`, `get_board_infos`, `get_warnings`.
    - `would_create_dependency_cycle` returns `False`.
    - Board, column, category and dependency writes raise `NotImplementedError`, as `ClaudeBackend` does.

- [ ] **Step 1: Set up the fork.** Fork `Zaloog/kanban-tui` to `AdrianV101`, clone it to `~/Projects/kanban-tui`, add the `upstream` remote, and create branch `vault-backend`. Run `uv sync --all-extras` and `make test`. Expected: all existing tests pass before any change.
- [ ] **Step 2: Write the failing tests.**
  - **1.1 Which notes become cards.** Only notes with `type: task` under the configured globs become cards. The population:
    - A task in `01-Projects/X/tasks/`: shown.
    - A task directly in `00-Inbox/`: shown.
    - A task in `00-Inbox/audio-ingestion/`: hidden.
    - `05-Templates/task.md`: hidden.
    - A task in `04-Archive/`: hidden.
    - A `type: research` note inside a tasks folder: hidden.
    - A vault with no task notes gives an empty board, not an error.
  - **1.2 Status maps to column.** Each of the six statuses lands in its column (parametric over all six).
  - **1.3 Missing or unknown status.** A note with no status, or a status outside the six (`approved`, `superseded`), shows in Proposed. Its card metadata carries `unknown_status` with the original value.
  - **1.4 Board shape.** There is exactly one board, named `Vault`. Its columns run Proposed, Ready, Doing, In Review, Done, Archive, with Archive not visible. Reset, start and finish columns are 2, 3 and 5.
  - **1.5 Categories.** The category name comes from `project`, then from the folder name under `01-Projects/`, then from `personal_category` for `00-Inbox/`. The colour comes from `project_colors`, or else a fixed palette by first-seen order. A project keeps the same category id within one backend instance, even after a later scan adds a new project.
  - **1.6 Card fields.**
    - Title is the first `# ` heading, or else the filename without `.md`.
    - Description is the text under `## Description`, up to the next `## `.
    - `due_date` comes from `due`.
    - `creation_date` comes from `created`, or else the file modification time.
    - An unparseable `due` or `created` gives no date for that field and one warning naming the note.
  - **1.7 Ordering.** Cards in a column are ordered by priority (urgent, high, normal, low, missing), then by due date (earliest first, none last), then by `created` (oldest first). The `position` values run 0, 1, 2 in that order.
  - **1.8 Done window.** With today frozen, a `done` note shows if its `finished` date is within `done_visible_days`. A note with no `finished` uses the file modification time instead. An older done note is not returned.
  - **1.9 Unreadable notes.** A matched note with unreadable bytes or malformed frontmatter is skipped. It's named in `get_warnings()`, and the other cards still load.
  - **1.10 Lookups use the last scan.** `get_task_by_id` and `get_tasks_by_ids` return the last scan's values, even if a file changed on disk since. Task ids stay the same for the same note across scans in one backend instance.
  - **1.11 (app) Warnings are visible.** With `vault_app` and one malformed note, mounting the board shows a notification that names the note. The good cards are on the board.
  - **1.12 (app) Switching to the vault backend is refused when it can't load.** Switching through the backend selector with an empty or missing `vault_path`, or with PyYAML not installed (observed through `importlib.metadata.version`), shows a warning. The previous backend stays active (parametric over the three).
- [ ] **Step 3: Run the tests.** `uv run pytest tests/backends/vault/test_vault_read.py tests/app_tests/test_vault_backend_integration.py --no-cov`. Expected: they fail, because `Backends.VAULT` and `VaultBackend` don't exist yet.
- [ ] **Step 4: Implement** the settings, `notes.read_task_note`, the read side of `VaultBackend`, and the app cases.
  - Scan with `Path.glob` per pattern, de-duplicated, and keep the result for lookups.
  - Assign ids from a `rel_path -> id` map that only grows for the backend's lifetime.
  - Parse frontmatter with `yaml.safe_load` on the block between the first two `---` lines.
- [ ] **Step 5: Run the tests.** Same command. Expected: pass. Then `make test` and `make check`. Expected: all green.
- [ ] **Step 6: Commit** with the message "feat(vault): read vault task notes as a six-column board".

### Task 2: Moving a card writes the note

**Files:**
- Modify: `src/kanban_tui/backends/vault/notes.py`: add `with_status`.
- Modify: `src/kanban_tui/backends/vault/backend.py`: add `update_task_status`.
- Test: `tests/backends/vault/test_vault_move.py` and `tests/app_tests/test_vault_backend_integration.py`.

**Interfaces:**
- Consumes: the `TaskNote` and `note_path` metadata from Task 1.
- Produces:
  - `notes.with_status(text: str, status: str, finished: date | None) -> str` returns the text with only the `status` value replaced. When `finished` is given, it also replaces or inserts a `finished` line at the end of the frontmatter.
  - `VaultBackend.update_task_status(new_task: Task, target_position: int | None = None, append_mode: TaskAppendModes | None = None) -> Task | dict[str, Any]` returns the updated `Task` on success.
  - On refusal it returns `{"success": False, "message": str}`. That's the shape `KanbanBoard.action_confirm_move` already reports as "Status Update Failed".
  - `target_position` and `append_mode` are ignored.

- [ ] **Step 1: Write the failing tests.**
  - **2.1 A move writes the column's status.** Moving a card to each of the six columns writes that column's status. The next `get_tasks_on_active_board()` shows the card there (parametric over the six).
  - **2.2 Only the status line changes.** The file after a move equals the file before, except for the status value, plus the `finished` line when entering Done. The population:
    - Plain `status: pending`.
    - Quoted `status: "pending"`.
    - `status: pending  # note`.
    - Status as the last frontmatter line.
    - A tags list and wikilinks in the body.
    - A file with no trailing newline.
  - **2.3 A changed status on disk refuses the move.** If the status on disk differs from the one the card was scanned with, the move returns the failure dict naming the note, and the file is byte-identical afterwards.
  - **2.4 Other changes on disk are kept.** If only the body or other fields changed since the scan, the move succeeds and those changes are preserved.
  - **2.5 A missing note refuses the move.** If the note was deleted or renamed since the scan, the move returns the failure dict, and no file is created.
  - **2.6 (app) Pressing a move key writes the note.** In `vault_app`, pressing `L` on a focused Ready card moves it to Doing on screen, and the note on disk says `status: active`.
  - **2.7 (app) A refusal is shown.** After the note's status is changed on disk, pressing `L` shows "Status Update Failed". The card stays in its column.
- [ ] **Step 2: Run the tests.** `uv run pytest tests/backends/vault/test_vault_move.py tests/app_tests/test_vault_backend_integration.py --no-cov`. Expected: the new tests fail with `NotImplementedError` or `AttributeError`.
- [ ] **Step 3: Implement** `with_status` and `update_task_status`.
  - Re-read the file immediately before writing, and compare its status with the card's `metadata["status"]`.
  - Write to a temporary file in the same folder, then replace the original with `os.replace`.
  - Set `finished` to today when the target is Done.
- [ ] **Step 4: Run the tests.** Same command, then `make test` and `make check`. Expected: all green.
- [ ] **Step 5: Commit** with the message "feat(vault): moving a card writes the note's status".

### Task 3: Creating a card writes a new task note

**Files:**
- Modify: `src/kanban_tui/backends/vault/notes.py`: add `render_new_task` and `note_filename`.
- Modify: `src/kanban_tui/backends/vault/backend.py`: add `create_new_task` and `VaultWriteError`.
- Modify: `src/kanban_tui/widgets/board_widgets.py`:
  - `action_new_task` passes the target column.
  - `place_new_task` places the card in that column.
- Modify: `src/kanban_tui/modal/modal_task_screen.py`:
  - It accepts `column: int | None`.
  - It catches `VaultWriteError`, shows the error, and stays open with the input kept.
- Test: `tests/backends/vault/test_vault_create.py` and `tests/app_tests/test_vault_backend_integration.py`.

**Interfaces:**
- Consumes: the category id-to-name map and each project's learned tasks folder (from Task 1's scan), and `STATUS_COLUMNS`.
- Produces:
  - `notes.note_filename(title: str) -> str` returns a kebab-case name with `.md`, falling back to `task.md`.
  - `notes.render_new_task(template_text: str, title: str, status: str, project: str | None, due: date | None, description: str, today: date) -> str`:
    - It substitutes `2026-11-04` and `2026-11-04-kanban-vault-backend-plan`.
    - It sets `status`, `project` and `due`.
    - It puts `description` under `## Description`.
  - `VaultBackend.create_new_task(title: str, description: str, column: int, category: int | None = None, due_date: datetime | None = None) -> Task`:
    - It raises `VaultWriteError(message: str)` when it refuses.
    - The modal passes `due_date` as an ISO string. Accept both types, as sqlite does.
  - For the vault backend, the new-task column is the focused card's column. With no focused card, it's Ready (2). Other backends keep the first visible column.

- [ ] **Step 1: Write the failing tests.**
  - **3.1 A new card becomes a full task note.**
    - The note is rendered from the vault's `05-Templates/task.md`, with today's date and the title substituted.
    - It carries the column's status, the category's project and the due date. The description sits under `## Description`.
    - It's written to that project's learned tasks folder, or to `00-Inbox/` for the personal category. Parametric over `Work`, `Side Project` and Personal.
  - **3.2 Filenames are safe and never overwrite.**
    - The filename is the kebab-case title: `Fix: flaky/CI test` becomes `fix-flaky-ci-test.md`.
    - Emoji are dropped, and a symbol-only title gives `task.md`.
    - A clash gets `-2`, then `-3`.
    - An existing file is never overwritten.
  - **3.3 Creation is refused when it can't be done correctly.** A missing template or a project with no known tasks folder raises `VaultWriteError`, and no file is written.
  - **3.4 (app) Cards land where they were made.** In `vault_app`, pressing `n` with a card focused in column X, typing a title and continuing puts a card in column X with a matching note on disk. With no card focused, the card goes to Ready. Parametric over Proposed, Ready and Doing.
  - **3.5 (app) A refused creation keeps the input.** When creation is refused (template removed), an error notification shows, and the modal stays open with the typed title.
- [ ] **Step 2: Run the tests.** `uv run pytest tests/backends/vault/test_vault_create.py tests/app_tests/test_vault_backend_integration.py --no-cov`. Expected: the new tests fail.
- [ ] **Step 3: Implement** `note_filename`, `render_new_task`, `create_new_task`, and the board and modal changes. Gate the board and modal changes on `Backends.VAULT`, matching the file's existing `backend.mode` checks.
- [ ] **Step 4: Run the tests.** Same command, then `make test` and `make check`. Expected: all green, including the unchanged sqlite new-task tests.
- [ ] **Step 5: Commit** with the message "feat(vault): create task notes from the board".

### Task 4: Archive and open notes from the board

**Files:**
- Modify: `src/kanban_tui/backends/vault/backend.py`:
  - `delete_task` sets `cancelled` through the Task 2 write path.
  - It raises `VaultWriteError` on refusal.
  - It adds `note_url(task: Task) -> str`.
- Modify: `src/kanban_tui/widgets/task_card.py`:
  - For the vault backend, `action_edit_task` calls `self.app.open_url(backend.note_url(task))` instead of pushing the edit modal. This covers `e`, `enter` and click.
  - `action_delete_task` shows "Archive task …? The note is kept." with the button "Archive task".
- Modify: `src/kanban_tui/widgets/board_widgets.py`: for the vault backend, `delete_task` calls the backend first. It removes the card only on success, and otherwise shows the error.
- Test: `tests/backends/vault/test_vault_archive.py` and `tests/app_tests/test_vault_backend_integration.py`.

**Interfaces:**
- Consumes: `update_task_status` and its refusal rule from Task 2.
- Produces:
  - `VaultBackend.delete_task(task_id: int) -> None`.
  - `VaultBackend.note_url(task: Task) -> str` returns `obsidian://open?vault=<vault folder name>&file=<rel path without .md>`, with both values URL-encoded.

- [ ] **Step 1: Write the failing tests.**
  - **4.1 Archiving keeps the note.** `delete_task` sets the note's status to `cancelled`. The file still exists, and the card is gone from the next scan, because Archive is hidden.
  - **4.2 The Obsidian link is right.** `note_url` gives the exact URI for `01-Projects/Side Project/tasks/a b.md` in vault folder `Notes`, with spaces and `/` encoded.
  - **4.3 (app) Archiving from the board.** In `vault_app`, pressing `d` shows the Archive wording, and `enter` confirms. Afterwards the card is gone and the note says `status: cancelled`.
  - **4.4 (app) A refused archive is shown.** After the note's status is changed on disk, an archive attempt shows the error. The card stays on the board and the file is unchanged.
  - **4.5 (app) Edit opens Obsidian.** On a vault card, `e`, `enter` and a click each open the note's URI, observed at the browser boundary (`webbrowser.open` monkeypatched to record). `ModalTaskEditScreen` is not pushed (parametric over the three).
- [ ] **Step 2: Run the tests.** `uv run pytest tests/backends/vault/test_vault_archive.py tests/app_tests/test_vault_backend_integration.py --no-cov`. Expected: the new tests fail.
- [ ] **Step 3: Implement** `delete_task`, `note_url`, and the card and board changes, gated on `Backends.VAULT`.
- [ ] **Step 4: Run the tests.** Same command, then `make test` and `make check`. Expected: all green, including the unchanged sqlite and claude delete and edit tests.
- [ ] **Step 5: Commit** with the message "feat(vault): archive cards and open notes in Obsidian".

### Task 5: Document, install and check on a vault copy

**Files:**
- Modify: `README.md`: add a Vault backend section covering the columns and statuses, the settings, `kanban-tui[vault]`, and what's unsupported (boards, columns, categories, dependencies, reordering, CLI and MCP).

- [ ] **Step 1: Write the README section.** Commit with the message "docs: vault backend".
- [ ] **Step 2: Push the branch** to the fork, and open a draft PR into the fork's own `main` (not upstream).
- [ ] **Step 3: Install it on the MacBook.** Run `uv tool install "kanban-tui[vault] @ git+https://github.com/AdrianV101/kanban-tui@vault-backend"`. Expected: `ktui info` runs.
- [ ] **Step 4: Check it against a copy of the vault.**
  - Copy `<vault>` to the scratchpad.
  - Set `backend.mode = "vault"`, `vault_settings.vault_path` to the copy, and `board.auto_refresh_interval = 60` in the kanban-tui config.
  - Run `ktui`.
  - Expected:
    - The open tasks appear in Ready and Doing, coloured by project.
    - A move changes only that note's status line (`diff` against the original).
    - `n` creates a note in the right folder.
    - `e` opens the note's copy in Obsidian.
- [ ] **Step 5: Report** the result to the owner. Pointing `vault_path` at the real vault waits for vault-pkm's enum change (part 2).
