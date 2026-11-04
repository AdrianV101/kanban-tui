# Kanban Board Field Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The vault board maps its columns from `status` plus a new `board` field, so it never writes a status vault-pkm doesn't know, and Claude's board behaviour lives in the owner's local CLAUDE.md.

**Architecture:** The backend's status-to-column table becomes two small functions. One reads a column from `status` and `board`. The other gives the `status` and `board` values for a target column. Moves, creates and archives all write through them, and the line-level frontmatter edit gains the `board` line next to `status` and `finished`. vault-pkm is not touched.

**Tech Stack:** Python 3.11+, Textual 8, PyYAML, pytest, freezegun, ruff, mypy.

**Spec:** [design](../design.md) , sections "Columns map to `status` and `board`", "No vault-pkm changes" and "Existing tasks need no migration". This supersedes the status values in [part 1 plan](2026-11-04-vault-backend.md).

## Global Constraints

- Repo `~/Projects/kanban-tui`, branch `vault-backend` (fork `AdrianV101/kanban-tui`, draft PR #1). Head before this plan: `1f6edaa`.
- `status` values written are only vault-pkm's four: `pending`, `active`, `done`, `cancelled`.
- Column mapping when reading:
  - `pending` with `board: ready` is Ready (2). Any other `pending` is Proposed (1), whether `board` is absent, `proposed` or anything else.
  - `active` with `board: in-review` is In Review (4). Any other `active` is Doing (3).
  - `done` is Done (5) and `cancelled` is Archive (6), whatever `board` says.
  - A missing or unknown status is Proposed, with `unknown_status` in the card metadata, as today.
- Fields written per target column:
  - Proposed writes `pending` and `proposed`.
  - Ready writes `pending` and `ready`.
  - Doing writes `active` and `doing`.
  - In Review writes `active` and `in-review`.
  - Done writes only `status: done`, plus the `finished` line as today.
  - Archive writes only `status: cancelled`.
- A write changes only the `status` line, the `board` line (replaced, or inserted at the end of the frontmatter) and the `finished` line on entering Done. Every other byte is kept.
- A move or archive is refused when the note's column on disk, worked out from its current `status` and `board`, differs from the column the card was scanned in.
- Every refusal stays visible, as today. The board never deletes a note file.
- vault-pkm (`~/Projects/obsidian-pkm-plugin`) is not changed.
- `make test` green. No new ruff findings. mypy stays at upstream's 152 errors. Run uv with `--frozen`. No AI attribution in commits.
- Tests that pin the old `proposed` and `in-review` status values encode the superseded design. Change them to the new mapping; don't keep both.

## Review Focus

1. A stale `board` on a done or cancelled note (for example `board: ready` with `status: done`). It shows in Done or Archive, and moving it back to Ready writes `board: ready` again. (Task 1, test 1.1; Task 2, test 2.1)
2. An inconsistent pair, such as `pending` with `board: in-review`. It shows in Proposed, not In Review. (Task 1, test 1.1)
3. A `board` value that is quoted or carries a trailing comment. It reads correctly, and a move keeps the quoting style. (Task 2, test 2.2)
4. Someone changes only `board` in Obsidian between scan and move (Ready to Proposed). The move is refused, the same as for a status change. (Task 2, test 2.3)
5. A note created on the board in Proposed, then opened in vault-pkm tools. It carries only valid statuses, so vault-pkm can update it. (Task 2, test 2.4)

---

### Task 1: Read columns from `status` and `board`

**Files:**
- Modify: `src/kanban_tui/backends/vault/notes.py`: `TaskNote` gains `board: str | None`.
- Modify: `src/kanban_tui/backends/vault/backend.py`: replace `STATUS_COLUMNS` with the functions below. Keep `COLUMN_NAMES`. The board's reset, start and finish columns stay 2, 3 and 5.
- Test: `tests/backends/vault/test_vault_read.py`.

**Interfaces:**
- Produces:
  - `column_for(status: str | None, board: str | None) -> int`.
  - `fields_for_column(column: int) -> tuple[str, str | None]` returns `(status, board)`. `board` is `None` for Done and Archive.
  - Card metadata keeps `status`, and adds `board` (as scanned) and `column` (the scanned column number).

- [ ] **Step 1: Rewrite the failing tests.**
  - **1.1 Column mapping.** Parametric over these `(status, board)` pairs and their expected columns:
    - `(pending, absent)` gives 1.
    - `(pending, "proposed")` gives 1.
    - `(pending, "ready")` gives 2.
    - `(pending, "in-review")` gives 1.
    - `(pending, "junk")` gives 1.
    - `(active, absent)` gives 3.
    - `(active, "doing")` gives 3.
    - `(active, "ready")` gives 3.
    - `(active, "in-review")` gives 4.
    - `(done, "ready")` gives 5.
    - `(done, absent)` gives 5.
    - `(cancelled, "in-review")` gives 6.
  - **1.2 Missing or unknown status.** A missing status, `approved` and `superseded` all land in Proposed with `unknown_status`. This is the existing test, with `board` absent and present.
  - **1.3 Scanned values are recorded.** Card metadata carries the scanned `status`, `board` and `column`.
- [ ] **Step 2: Run.** `uv run --frozen pytest tests/backends/vault/test_vault_read.py --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement** `column_for`, `fields_for_column` and `TaskNote.board`, and use them in `_note_to_task`.
- [ ] **Step 4: Run.** The same file, then `make test`. Other vault tests that pinned the old statuses may now fail; Task 2 owns them. Note which ones in the report.
- [ ] **Step 5: Commit** with the message "feat(vault): map columns from status and a board field".

### Task 2: Moves, creates and archives write `status` and `board`

**Files:**
- Modify: `src/kanban_tui/backends/vault/notes.py`: `with_status(text, status, finished)` becomes `with_card_fields(text: str, status: str, board: str | None, finished: date | None) -> str`.
  - `board=None` leaves any `board` line untouched.
  - Otherwise it replaces the `board` value in place, or inserts `board: <value>` at the end of the frontmatter.
  - `render_new_task` takes `board: str | None` and sets it the same way.
- Modify: `src/kanban_tui/backends/vault/backend.py`:
  - `update_task_status`, `create_new_task` and `delete_task` take their values from `fields_for_column`.
  - The conflict check compares `column_for(status on disk, board on disk)` with `metadata["column"]`.
  - After a successful write, the card's metadata gets the new `status`, `board` and `column`.
- Modify: `README.md` "Vault backend" section: the mapping table, `board`, and `prs` as an optional field the board ignores.
- Test: `tests/backends/vault/test_vault_move.py`, `test_vault_create.py`, `test_vault_archive.py` and `tests/app_tests/test_vault_backend_integration.py`.

**Interfaces:**
- Consumes: `column_for`, `fields_for_column` and metadata `column` from Task 1.

- [ ] **Step 1: Rewrite the failing tests.**
  - **2.1 Moves write the column's fields.** A move to each of the six columns writes the Global Constraints values to disk. Done and Archive leave an existing `board` line byte-identical. The next scan shows the card in the target column. Parametric over the six columns, plus a done note with stale `board: ready` moved to Ready.
  - **2.2 Only the owned lines change.** The existing byte-preservation population, plus:
    - `board` absent, so the line is inserted at the end of the frontmatter.
    - `board: doing`, replaced.
    - `board: "ready"`, quotes kept.
    - `board: ready  # note`, comment kept.
    - An empty `board:`.
  - **2.3 A changed column on disk refuses the move.** If the status or only the board changed on disk since the scan (Ready to Proposed by editing `board`), the move returns the failure dict and the file is byte-identical. Parametric over the two cases.
  - **2.4 Created notes carry the column's fields.** A card created in Proposed, Ready or Doing gets that column's `status` and `board`. Its status is one of vault-pkm's four. This replaces the status assertion in the existing 3.1.
  - **2.5 Archive.** Archiving sets `status: cancelled`, leaves `board` untouched, keeps the file, and refuses on a changed column. This updates the existing 4.1 and 4.4.
  - **2.6 (app) Moves through the TUI.** `L` on a Ready card writes `status: active` and `board: doing`. This updates the existing 2.6. The refusal toast test (2.7) runs unchanged on the new conflict rule.
- [ ] **Step 2: Run.** `uv run --frozen pytest tests/backends/vault tests/app_tests/test_vault_backend_integration.py --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement** `with_card_fields`, the `render_new_task` change, the three call sites, and the README section.
- [ ] **Step 4: Run.** The same command, then `make test`, `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .` and `uv run --frozen mypy . | tail -1`. Expected: all green, and mypy at 152.
- [ ] **Step 5: Commit** with the message "feat(vault): write status and board for moves, creates and archives".

### Task 3: Local Claude rules, reinstall and check (controller, not a subagent)

- [ ] **Step 1:** Add the rules below to the owner's `~/.claude/CLAUDE.md`, under a "Kanban board" heading in the Docs and Notes area. The wording is agreed with the owner before it's written.
- [ ] **Step 2:** Push `vault-backend`. Before pushing, fetch and merge the remote branch. Then run `uv tool upgrade kanban-tui` and confirm `ktui` starts.
- [ ] **Step 3:** Check headlessly against a fresh copy of the task folders and the template, in the scratchpad.
  - Column counts: Proposed holds the open pending tasks, Doing holds the active ones.
  - A move to Ready changes exactly the `status` and `board` lines.
  - A move to In Review writes `active` and `in-review`.
  - No status outside vault-pkm's four is written anywhere.

**Rules for `~/.claude/CLAUDE.md` (draft):**

- Task notes carry an optional `board` field for the kanban board: `proposed`, `ready`, `doing` or `in-review`. Leave it out of tasks you create, so they land in Proposed. Set `board: ready` only on a task the owner asked for directly.
- Never set a task's `status` to `done`. Only the owner moves cards to Done. The PR merge job is the only other thing that sets it.
- When opening a draft PR for a task, set `board: in-review` and add the PR URL to the note's `prs` list. If the session has no task note, create one with `status: active`, `board: in-review` and the PR in `prs`.
- When dispatching pkm-capture, include these rules in its prompt.
