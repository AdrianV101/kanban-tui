# Vault Board Mac Mini Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two scheduled jobs on the Mac mini keep the vault board current. An hourly PR check moves In Review cards when their PRs close. A morning sweep turns phone captures and meeting action items into Proposed drafts. A phone Shortcut feeds `00-Inbox/Capture.md`.

**Architecture:** Both jobs are subcommands of a new fork-only `vault-board` command in the kanban-tui fork, so every note write goes through the vault backend's conflict-checked write path. The PR check is plain Python over `gh`. The sweep runs one headless `claude -p` that may only read Granola and Plaud. It returns drafts as JSON, and the script writes the notes, removes captured lines and keeps a small state file. De-duplication and "a line leaves `Capture.md` only after its draft exists" are therefore enforced by code, not by the prompt. Two LaunchAgents schedule the jobs. Personal settings (vault path, owner name, GitHub accounts) live in a config file on the Mac mini, not in the public fork.

**Tech Stack:** Python 3.11+ (tomllib, subprocess), click, PyYAML, pytest, freezegun, ruff, mypy, `gh`, Claude Code CLI, launchd.

**Spec:** [design](../design.md), sections "Who moves what", "Capture sources", "Scheduled jobs run on the Mac mini" and "Constraints".

## Calls this plan makes (Claude's calls)

- The code lives in the fork on branch `vault-backend`, under `src/kanban_tui/backends/vault/jobs/`, with its own console script `vault-board`. It is fork-only like `docs/vault-board/` and gets dropped before the backend is offered upstream. The jobs reuse the backend's conflict-checked writes. The Automation daemon is not touched.
- The sweep's Claude run gets no vault tools. It reads Granola and Plaud and returns drafts, and the script writes them. This narrows the design's "with vault-pkm available".
- The PR check runs every hour. The sweep runs daily at 06:30. Both also run when the Mac mini boots, so a reboot catches up. Both are safe to rerun.
- "Merged" means GitHub reports the PR as `MERGED`, whatever its base branch. Mergify merges count.
- A failure card is made at most once per source per day.
- The first sweep looks back two days. Later sweeps look back from one day before that source's last successful run.

## Global Constraints

- Repo `~/Projects/kanban-tui`, branch `vault-backend`, head `cfc2027` before this plan. Draft PR #1 stays the review surface.
- New code goes in `src/kanban_tui/backends/vault/jobs/`, tests in `tests/backends/vault/jobs/`, and ops files in `docs/vault-board/jobs/`. The console script is `vault-board = "kanban_tui.backends.vault.jobs.cli:main"`.
- Every note write goes through `VaultBackend`: `create_new_task`, `update_task_status` or the new `move_with_note`. Removing lines from `Capture.md` uses the same stat-checked atomic replace. Nothing deletes a note.
- Only vault-pkm's four statuses are written. The PR check is the only writer of `done` besides the owner.
- PR check rule:
  - Every PR in `prs` closed and at least one merged: Done.
  - Every PR closed and none merged: back to Doing (`status: active`, `board: doing`) plus one appended line.
  - Any PR still open, or any PR the check can't read: the card is left alone.
- The sweep's Claude run may use only these tools: `mcp__granola__list_meetings`, `mcp__granola__search_meetings`, `mcp__granola__get_meetings`, `mcp__granola__get_meeting_transcript`, `mcp__granola__search_transcripts`, `mcp__plaud__list_files`, `mcp__plaud__get_file`, `mcp__plaud__get_note` and `mcp__plaud__get_transcript`. If the Mac mini's servers expose other names, Task 7 corrects this list.
- No personal details in the fork. The owner's name, GitHub account and org names, the vault name and home paths live in `~/.config/vault-board/jobs.toml` on the Mac mini. The fork ships `docs/vault-board/jobs/jobs.example.toml` with placeholders.
- Dates come from `date.today()`. Never use `ZoneInfo("localtime")`, which silently resolves to UTC under launchd on macOS.
- Tests never run the real `gh` or `claude` and never read the real vault. The adapters take an injected command runner.
- `make test` is green, there are no new ruff findings, and mypy stays at 152. Run uv with `--frozen`. Add no dependencies. No AI attribution in commits.
- vault-pkm is not changed.

## Review Focus

1. A phone capture syncs into `Capture.md` while the sweep removes processed lines. The new line stays. (Task 3, test 3.2)
2. The Mac mini was off at 06:30, or the sweep runs twice in one day. There are no duplicate drafts and no second failure card. (Task 5, tests 5.2 and 5.4)
3. A PR that the mapped account can't see, or `gh` signed out. The card stays in In Review, the log names the PR, and other cards still move. (Task 2, tests 2.3 and 2.5)
4. The owner moves a card out of In Review while the check runs. The check's write is refused and the owner's move stands. (Task 2, test 2.4)
5. One meeting recorded in both Granola and Plaud. It gets one set of drafts, from Granola. (Task 4, test 4.3 pins the rule in the prompt.)

---

### Task 1: Backend support for the jobs

**Files:**
- Modify: `src/kanban_tui/backends/vault/notes.py`, `src/kanban_tui/backends/vault/backend.py`.
- Test: `tests/backends/vault/test_vault_read.py`, `test_vault_create.py`, `test_vault_move.py`.

**Interfaces:**
- Produces:
  - `TaskNote.prs: list[str]`, and card metadata `prs`.
  - `render_new_task(..., source: str | None)`. It sets `source` the way it sets `project`, quoting a value that isn't a safe scalar.
  - `VaultBackend.create_new_task(..., *, source: str | None = None) -> Task`.
  - `with_appended_line(text: str, line: str) -> str` in `notes.py`. It appends `line` as the note's last line, adding a line break first if the text doesn't end with one, and uses the note's own line ending.
  - `VaultBackend.move_with_note(task: Task, column: int, line: str) -> Task | dict[str, Any]`. It runs the same checks and refusals as `update_task_status` and writes the column's fields and the line in one replace.
  - `VaultBackend.writable_projects() -> dict[str, int | None]`. It maps each project that has a known tasks folder to its category id, plus the Personal category to `None`.

- [ ] **Step 1: Write the failing tests.**
  - **1.1 `prs` parsing.** Parametric:
    - A list of URLs gives that list.
    - A single string gives a one-item list.
    - Absent or `null` gives `[]`.
    - A list holding a non-string, or a mapping, gives `[]` with `prs` in `invalid_fields`.
    - The card's metadata carries the parsed list.
  - **1.2 `source` on create.** Parametric over absent, a plain word and a URL with a colon. The note parses back with that `source`. Absent leaves the template's `source: null` line byte-identical.
  - **1.3 Move with a note line.** `move_with_note` writes the target column's `status` and `board`, and the line as the note's last line. It is parametric over notes ending with a line break, without one, and with CRLF. Every other byte is kept, and the next scan shows the card in the target column.
  - **1.4 Refusal.** `move_with_note` returns the failure dict and leaves the file byte-identical when the column on disk changed since the scan.
  - **1.5 Writable projects.** `writable_projects()` lists each project with a known tasks folder and Personal. Creating a card with each listed id lands the note in that project's tasks folder, or in `00-Inbox` for Personal.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement.** `update_task_status` and `move_with_note` share one private move path.
- [ ] **Step 4: Run** the same command, then `make test`.
- [ ] **Step 5: Commit** with the message "feat(vault): read prs, set source on create, move with a note line".

### Task 2: Hourly PR check

**Files:**
- Create: `src/kanban_tui/backends/vault/jobs/__init__.py`, `jobs/github.py`, `jobs/pr_check.py`.
- Test: `tests/backends/vault/jobs/test_github.py`, `test_pr_check.py`.

**Interfaces:**
- Consumes: metadata `prs`, `column` and `note_path`, plus `update_task_status` and `move_with_note` from Task 1.
- Produces:
  - `Runner`: a callable taking an argv list and a dict of extra environment variables, returning `(exit_code, stdout, stderr)`. A timeout raises `subprocess.TimeoutExpired`. Task 4 uses it too.
  - `PrRef(owner: str, repo: str, number: int)` and `parse_pr_url(url: str) -> PrRef | None`.
  - `PrState = Literal["OPEN", "CLOSED", "MERGED"]` and `PrFetchError(Exception)`.
  - `GhPrStates(accounts: dict[str, str], run: Runner)` with `state(url: str) -> PrState`.
  - `check_prs(backend: VaultBackend, fetch: Callable[[str], PrState], today: date) -> PrCheckReport`. The report has `done: list[str]` and `reopened: list[str]` (note paths), `skipped: list[tuple[str, str]]` (note path, reason), and `ok: bool`. `ok` is false when any card was skipped for an error. A card left alone because a PR is still open is not a skip.
  - The appended line is exactly ``- {today}: every PR in `prs` closed without merging. The PR check moved this card back to Doing.``

- [ ] **Step 1: Write the failing tests.**
  - **2.1 Decision rule.** Parametric over the PR states of an In Review card:
    - `[OPEN]` and `[OPEN, MERGED]` leave the file byte-identical.
    - `[MERGED]` and `[CLOSED, MERGED]` write `status: done` and `finished: <today>`.
    - `[CLOSED]` and `[CLOSED, CLOSED]` write `status: active`, `board: doing` and the pinned line.
    - Each moved card shows in the matching column on the next scan.
  - **2.2 Scope.** Only In Review cards are checked. Cards in the other five columns that carry `prs` are never fetched. A PR URL shared by two cards is fetched once per run.
  - **2.3 Skips leave the note alone.** Parametric over empty `prs`, invalid `prs`, a URL that isn't a GitHub PR, and a fetch error on one of two PRs. The file stays byte-identical, the report names the note and the reason, and other In Review cards are still moved.
  - **2.4 Concurrent move.** The fake fetch edits the note to `board: doing` before returning `MERGED`. The write is refused, the edit stands, and the report lists the refusal.
  - **2.5 `GhPrStates`.** Parametric, with a recording runner:
    - An owner listed in `accounts`, matched case-insensitively, runs `gh auth token --user <account>` once per account per instance. The token goes in `GH_TOKEN` for `gh pr view <url> --json state`.
    - An owner not listed runs `gh pr view` with no `GH_TOKEN` override.
    - A non-zero exit, unreadable JSON or a state outside the three raises `PrFetchError` carrying gh's stderr.
  - **2.6 `parse_pr_url`.** Parametric:
    - These give `("o", "r", 12)`: `https://github.com/o/r/pull/12`, the same with a trailing slash, with `/files`, and with a query or fragment.
    - An issue URL, a non-GitHub host and a non-URL give `None`.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault/jobs --no-cov`. Expected: fail.
- [ ] **Step 3: Implement** `github.py` and `pr_check.py`.
- [ ] **Step 4: Run** the same command, then `make test`.
- [ ] **Step 5: Commit** with the message "feat(vault): hourly PR check moves In Review cards when their PRs close".

### Task 3: Capture file and sweep state

**Files:**
- Create: `jobs/capture.py`, `jobs/sweep_state.py`.
- Test: `tests/backends/vault/jobs/test_capture.py`, `test_sweep_state.py`.

**Interfaces:**
- Produces:
  - `CAPTURE_PATH = "00-Inbox/Capture.md"`.
  - `CaptureItem(id: str, line: str, text: str)`. `id` is `c1`, `c2` and so on, in file order. `line` is the raw line without its line ending. `text` is the line with its bullet removed and whitespace trimmed.
  - `read_capture_items(vault: Path) -> list[CaptureItem]`.
  - `remove_capture_lines(vault: Path, lines: list[str]) -> None`. It removes the first occurrence of each given raw line and keeps every other byte. If the file changes between read and replace, it rereads and tries again, up to 3 attempts, then raises `CaptureWriteError`.
  - `SweepState` with four maps: `meetings` (key to the ISO date it was examined), `captures_written` (raw line to note path), `last_success` (source to ISO date) and `failure_cards` (card title to ISO date).
  - `load_state(path: Path) -> SweepState`, `save_state(path: Path, state: SweepState) -> None` and `StateError`. Saving creates the folder and writes a temp file in it, fsyncs, then replaces.
  - `prune(state: SweepState, today: date) -> None` drops meeting keys examined more than 14 days ago.

- [ ] **Step 1: Write the failing tests.**
  - **3.1 Reading captures.** Parametric over `- text`, `* text`, `- [ ] text`, plain `text` and surrounding whitespace. Blank lines are skipped, ids follow file order, and a missing file gives `[]`.
  - **3.2 Removing lines.**
    - The given lines are removed, and a line appended after the read is kept. The test simulates this by changing the file once between read and replace.
    - CRLF endings and every other byte are kept.
    - A missing file is a no-op.
    - A file that changes on every attempt raises `CaptureWriteError` after 3 attempts, with the file untouched by the sweep.
  - **3.3 State.**
    - A missing file loads as empty, and save then load round-trips.
    - Unreadable JSON or a wrong shape raises `StateError`. It never resets silently, because a reset would duplicate drafts.
    - `prune` drops meeting keys older than 14 days and keeps the rest.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault/jobs --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command, then `make test`.
- [ ] **Step 5: Commit** with the message "feat(vault): read and clear Capture.md, keep sweep state".

### Task 4: The sweep's Claude run

**Files:**
- Create: `jobs/sweep_agent.py`.
- Test: `tests/backends/vault/jobs/test_sweep_agent.py`.

**Interfaces:**
- Consumes: `Runner` from Task 2 and `CaptureItem` from Task 3.
- Produces:
  - `SweepRequest(today: date, owner_name: str, projects: list[str], captures: list[CaptureItem], since: dict[str, date], processed: list[str])`.
  - `Draft(source_key: str, title: str, project: str, context: str, link: str)`. Keys are `capture:<id>`, `granola:<meeting id>` or `plaud:<file id>`.
  - `AgentResult(drafts: list[Draft], examined: dict[str, list[str]], errors: dict[str, str | None])`. `examined` and `errors` are keyed by `granola` and `plaud`. `examined` holds bare ids.
  - `AgentError(Exception)`.
  - `build_prompt(request: SweepRequest) -> str`.
  - `run_agent(request: SweepRequest, claude_path: Path, model: str, run: Runner, timeout_s: int = 900) -> AgentResult`.
- The prompt states these rules:
  - Every capture item gets exactly one draft.
  - Meeting drafts are action items for the owner only.
  - A meeting goes in `examined` only when its notes were available.
  - Meetings listed in `processed` are skipped.
  - A meeting found in both Granola and Plaud is drafted from Granola only.
  - `project` is one of the given names, or `Personal`.
  - Titles are short imperatives.
  - Never call a tool that writes.
  - Reply with the JSON object only.

- [ ] **Step 1: Write the failing tests.**
  - **4.1 Command.** The argv is `<claude_path> -p <prompt> --output-format json --model <model> --allowedTools <the pinned list>`, run with the timeout. No other tool name appears.
  - **4.2 Parsing.** Parametric.
    - Accepted: the CLI's result envelope with the JSON object as `result`, and the same object wrapped in a json code fence.
    - `AgentError` for a non-zero exit, a timeout, `is_error: true`, a `result` that isn't JSON, a missing key and a wrong type.
  - **4.3 Prompt contents.** The prompt holds each capture id and text, the project names, the owner name, today, each source's `since`, the processed keys and each rule above.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault/jobs --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command, then `make test`.
- [ ] **Step 5: Commit** with the message "feat(vault): headless Claude run that drafts tasks from captures and meetings".

### Task 5: The sweep run

**Files:**
- Create: `jobs/sweep.py`.
- Test: `tests/backends/vault/jobs/test_sweep.py`.

**Interfaces:**
- Consumes: Tasks 1, 3 and 4.
- Produces: `run_sweep(backend: VaultBackend, state_path: Path, agent: Callable[[SweepRequest], AgentResult], owner_name: str, today: date) -> SweepReport`. The report has `created: list[str]` (note paths), `errors: dict[str, str]` (card title to error) and `ok: bool`.
- A run does these in order:
  1. Load the state. On `StateError`, make the "Capture sweep failed" card and stop.
  2. Remove lines whose raw text is already in `captures_written`, then drop those entries.
  3. Read the captures and build the request.
     - `projects` is `writable_projects()`.
     - Each source's `since` is its last success minus one day, or today minus two days.
     - `processed` is the state's meeting keys.
  4. Run the agent. On `AgentError`, make the "Capture sweep failed" card and stop with `Capture.md` untouched.
  5. Validate the drafts and drop the rest.
     - A capture key must name an item that was sent.
     - A meeting key must be in `examined`.
     - An unknown project becomes Personal.
  6. Write each draft in Proposed through `create_new_task`.
     - `context` is the description.
     - `source` is the link for a meeting draft when it starts with `https://`, else the key. For a capture draft it is `Capture.md <today>`.
     - Save the state after each note.
  7. Mark examined meetings whose drafts were all written, and remove the captured lines.
  8. Advance `last_success` for each source with no error. Make failure cards. Prune and save the state.
- Failure cards:
  - Proposed and Personal.
  - The titles are exactly "Capture sweep failed", "Capture sweep: Capture.md failed", "Capture sweep: Granola failed" and "Capture sweep: Plaud failed".
  - The description is the error, a blank line, then "The sweep tries again on its next run."
  - At most one per title per day, tracked in `failure_cards`.

- [ ] **Step 1: Write the failing tests.**
  - **5.1 Happy path.**
    - Capture and meeting drafts become Proposed notes with their title, description and `source`.
    - A known project's note lands in its tasks folder. Personal and unknown projects land in `00-Inbox`.
    - Captured lines leave `Capture.md`, and meeting keys are recorded.
  - **5.2 Rerun.** A second run with the agent returning the same drafts creates nothing new. The processed meetings reach the agent as `processed`.
  - **5.3 Crash recovery.** A line that is in `captures_written` but still in `Capture.md` is removed without being sent to the agent again.
  - **5.4 Source error.**
    - The error makes one card for that source, and other sources' drafts are still written.
    - `last_success` doesn't advance for that source.
    - A second run the same day makes no second card.
  - **5.5 Agent error.** It makes one "Capture sweep failed" card naming the error, leaves `Capture.md` byte-identical, adds no state keys, and the report is not ok.
  - **5.6 Invalid output.** Parametric:
    - A capture item with no draft stays in `Capture.md`, and a "Capture sweep: Capture.md failed" card names its text.
    - A draft with an unknown key, or for a meeting not in `examined`, is ignored.
  - **5.7 Write failure.** With the template missing, the item's line stays in `Capture.md`, its meeting stays unmarked, and the report names it.
  - **5.8 Unreadable state.** It makes one "Capture sweep failed" card and changes nothing else.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault/jobs --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command, then `make test`.
- [ ] **Step 5: Commit** with the message "feat(vault): morning sweep turns captures and meetings into Proposed drafts".

### Task 6: Command, config, schedules and docs

**Files:**
- Create: `jobs/config.py`, `jobs/cli.py`.
- Test: `tests/backends/vault/jobs/test_config.py`, `test_cli.py`.
- Modify: `pyproject.toml` `[project.scripts]`.
- Create in `docs/vault-board/jobs/`:
  - `jobs.example.toml`.
  - `com.vault-board.pr-check.plist.template` and `com.vault-board.sweep.plist.template`.
  - `install.sh`, `setup.md` and `phone-shortcut.md`.
- Modify: `docs/vault-board/README.md` (rows for parts 3 and 4, and the jobs install) and `docs/vault-board/progress.md`.

**Interfaces:**
- Consumes: Tasks 2 to 5.
- Produces:
  - `JobsConfig(vault_path: Path, owner_name: str, gh_accounts: dict[str, str], claude_path: Path, sweep_model: str, state_path: Path)`, `load_config(path: Path) -> JobsConfig` and `ConfigError`.
    - The default path is `~/.config/vault-board/jobs.toml`.
    - Defaults: `claude_path` is `~/.local/bin/claude`, `sweep_model` is `sonnet`, `state_path` is `~/.local/state/vault-board/sweep.json`.
    - `~` is expanded.
  - `vault-board pr-check [--config PATH]` and `vault-board sweep [--config PATH]`. Each prints one line per action and a summary. It exits 0 when the report is ok, 1 otherwise, and 2 on a config error.
- Ops files:
  - **Plists.** `com.vault-board.pr-check` runs every 3600 seconds and `com.vault-board.sweep` at 06:30. Both run at load. Their `PATH` is `~/.local/bin`, the Node bin folder found at install time, `/opt/homebrew/bin`, `/usr/bin` and `/bin`. Logs go to `~/Library/Logs/vault-board-pr-check.log` and `vault-board-sweep.log`.
  - **`install.sh`.** It fills the templates from the current shell: the home folder, and the Node bin folder from `command -v node`. It copies them to `~/Library/LaunchAgents` and reloads them with `launchctl bootout` and `launchctl bootstrap gui/$UID`. Rerun it after a Node upgrade.
  - **`setup.md`.** The Task 7 checklist, without personal values.
  - **`phone-shortcut.md`.**
    - Build an iOS Shortcut named Capture with two actions. Ask for Input takes text. Open URL opens `obsidian://new?vault=<vault>&file=00-Inbox%2FCapture&content=<"- " plus the input, URL-encoded>&append=true&spacing=newline&silent=true`.
    - Add it to the home screen.
    - Obsidian on the phone syncs only while it is open, so leave it in front for a few seconds after capturing.

- [ ] **Step 1: Write the failing tests.**
  - **6.1 Config.** Parametric:
    - A missing file gives `ConfigError` naming the path and the example file.
    - A missing `vault_path` or `owner_name`, or a `gh_accounts` that isn't a table, gives `ConfigError`.
    - Defaults and `~` expansion apply.
  - **6.2 CLI.** Uses `CliRunner`, with the adapters' runners replaced.
    - `pr-check` on a vault with nothing in review exits 0 and prints a summary.
    - `sweep` with an agent error exits 1.
    - A bad config exits 2 with the message on stderr.
- [ ] **Step 2: Run** `uv run --frozen pytest tests/backends/vault/jobs --no-cov`. Expected: the new cases fail.
- [ ] **Step 3: Implement** the code, the script entry and the ops files. Run `bash -n install.sh` and `plutil -lint` on both templates after filling them with sample values.
- [ ] **Step 4: Run** `make test`, `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .` and `uv run --frozen mypy . | tail -1`. Expected: all green, and mypy at 152.
- [ ] **Step 5: Commit** with the message "feat(vault): vault-board command, launchd schedules and setup docs".

### Task 7: Mac mini setup and first runs (on the Mac mini, not a subagent)

A Claude session on the Mac mini does this with the owner. It follows a runbook in the owner's private copy of this plan, which holds the account names and records a log that reaches other devices through Obsidian Sync. `docs/vault-board/jobs/setup.md` is the generic version.

- [ ] **Step 1:** Runbook Part A: GitHub work account, Granola and Plaud MCP servers, sign-ins, and a headless check of the tool names. It can run before the code exists.
- [ ] **Step 2:** Runbook Part B: install from `vault-backend`, write the config, run both jobs on a scratch copy, go live with the owner's go-ahead, install the schedules, and test a phone capture end to end. It runs after Tasks 1 to 6 are pushed.
- [ ] **Step 3 (MacBook):** Read the Mac mini log. If the tool names differ from the pinned list, fix the list and push. Then update the README status table, `progress.md` and the devlog, and push.
