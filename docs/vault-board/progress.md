# Progress

## Part 1: vault backend (done, 2026-11-04)

Commits `31e8a32`..`1f6edaa` on `vault-backend`, draft PR #1 into the fork's `main`. Built with subagent-driven development: one implementer and one reviewer per task, then a whole-branch review and one fix wave.

- 404 tests pass. ruff is clean. mypy stays at upstream's 152 errors.
- A headless check against a copy of the vault's task folders loaded 122 cards with no warnings. A move and an archive each changed one line. A new note landed in the right folder.
- The final review fixed:
  - A silent empty board on a bad `vault_path`.
  - A two-read overwrite window in moves.
  - A crash from the category editor in vault mode.
  - A wrong README line.
  - It also added fsync and a symlink refusal.

### Rulings made during part 1

Each ruling ends with what it costs if wrong.

1. Task 1 keeps a project-to-tasks-folder map that note creation uses. Cost: a small refactor.
2. Warnings show on mount and on refresh, not after every move. Cost: warnings shown less often.
3. Tests use a committed copy of the task template and never read the real vault. Cost: none.
4. Creating a card accepts the due date as a date or as text. Cost: none.
5. "Lint clean" means no new mypy errors versus upstream's 152. Cost: none.
6. uv.lock was regenerated once. The local uv also rewrote metadata (revision 5 to 3, `wrapt` markers). Cost: lockfile churn.
7. "No Category" means Personal, so the note goes to `00-Inbox`. Cost: a card meant for a project lands in the inbox.
8. The push, PR and install happened after the whole-branch review. Cost: a short wait.
9. fsync, the symlink refusal and a README auto-refresh note went into the final fix wave. Cost: a few lines.
10. Other minor findings stay deferred: test tidying, style, unrealistic edge cases. Cost: polish later.
11. A README wording nit about notes with an unknown status was left. Cost: one slightly misleading sentence.
12. The concurrent-edit check is a guard, not a lock, because Obsidian Sync takes no lock. Cost: an edit landing in the same microseconds as a move could be overwritten.
13. There's no directory fsync after a rename. Cost: a power cut at that instant could lose the rename.

### Design change after part 1

vault-pkm is a published plugin with other users, so the board must not need plugin changes. Its original `proposed` and `in-review` statuses are replaced by vault-pkm's four statuses plus a `board` field (see [design.md](design.md)). That is part 1b.

## Part 1b: board field (done, 2026-11-04)

Plan: [plans/2026-11-04-board-field.md](plans/2026-11-04-board-field.md). Ledger: [ledger-board-field.md](ledger-board-field.md). Commits `9bb80b3`..`81e9fd4`.

- Columns come from vault-pkm's four statuses plus a `board` field. No path writes any other status.
- 429 tests pass. ruff is clean. mypy stays at 152.
- A headless check against a copy of the vault's task folders gave:
  - Proposed 58, Doing 15, Done 1, Archive 48, with no warnings.
  - A move to Ready, then In Review, changed only the `status` line and added one `board` line.
  - Only that note changed.
- The final review said it's ready for daily use. Its one wording fix (a refusal now names both status and board) is in `81e9fd4`.

### Rulings made during part 1b

1. Tracking docs and the ledger are committed here, with personal details removed. Briefs, reports and diffs stay in the git-ignored workspace. Cost: per-task reports aren't visible on other devices.
2. One fix wave for the user-visible refusal wording only. The other minors stay deferred: duplicated mapping constants, one vacuous test row, case-sensitive values, and an unknown status in the same column being overwritten by a move. Cost: polish later.

## Part 2: local Claude rules (done, 2026-11-04)

Four rules were added under "Kanban board (vault task notes)" in the owner's global `~/.claude/CLAUDE.md`:
- Leave `board` out of tasks Claude creates.
- Never set `done`.
- Set `board: in-review` and record `prs` when opening a PR.
- Pass these rules to pkm-capture.

vault-pkm is unchanged.

## Part 3 and 4: Mac jobs and phone capture (code done, 2026-11-04)

Plan: [plans/2026-11-04-mac-mini-jobs.md](plans/2026-11-04-mac-mini-jobs.md). Ledger: [ledger-mac-mini-jobs.md](ledger-mac-mini-jobs.md). Commits `f0ffd5a`..`77aa6df`.

The `vault-board` command has two subcommands. `pr-check` moves In Review cards whose PRs have closed. `sweep` turns `Capture.md` lines and meeting action items into Proposed drafts. The launchd templates, `install.sh`, the config example and the phone Shortcut how-to are in `docs/vault-board/jobs/`. Mac setup steps: [jobs/setup.md](jobs/setup.md).

- 582 tests pass. ruff is clean. mypy stays at 152. uv.lock is unchanged.
- Built with subagent-driven development: one implementer and one reviewer per task, then a whole-branch review and one fix wave.
- The final review's fixes:
  - Every failure reaches the board as a card, including a missing `gh` or `claude` and an unreadable `Capture.md`.
  - Text from the model can't carry Templater blocks into notes, and titles stay on one line.
  - Bullet-only lines, Markdown headings and a frontmatter block in `Capture.md` are never treated as captures.
  - `setup.md` gained a launchd smoke test and notes on the Documents-folder prompt and staying logged in.

### Rulings made during parts 3 and 4

Each ruling ends with what it costs if wrong.

1. The sweep request carries project names; the sweep keeps the name-to-id map for writing. Cost: none.
2. The command runner lives in its own `jobs/runner.py`, shared by the gh and Claude adapters. Cost: one small file.
3. `last_success` and the look-back window cover only Granola and Plaud. Cost: none.
4. A capture already drafted is never sent to the model again, even if removing its line failed. Cost: a stuck line needs a manual delete.
5. Drafts from a source that also reported an error are still written; only its `last_success` holds back. Cost: a half-read meeting could be marked examined.
6. `gh` calls time out after 30 seconds and count as unreadable. Cost: a slow `gh` skips a card for an hour.
7. Removing capture lines reuses the backend's stat-checked replace. Cost: a private-name import.
8. `--allowedTools` gets one comma-separated argument. Cost: none, the Mac's headless check would catch it.
9. The sweep's Claude run also gets `--tools ""` and `--permission-mode dontAsk`, and the prompt says captured and meeting text is data, not instructions. This goes beyond the plan's argv. Cost: an older CLI rejects the flags, which the Mac's headless check catches.
10. A draft's project matches ignoring case; no match means Personal. Cost: none.
11. A failure card's date is still recorded when the agent fails, so the card stays once per day. Cost: none.
12. A meeting is recorded as done as soon as its first draft is written, overriding the plan's "after all its drafts". Reruns must never duplicate a draft. Cost: a failed later draft of that meeting isn't retried, but its card names it.
13. Model text has `<%` rewritten to `< %`, and titles collapse to one line. Drafts are not rejected. Cost: a capture that really contains `<%` reads slightly differently.
14. Headings, bullet-only lines and a leading frontmatter block in `Capture.md` are not captures and are never removed. Cost: none.
15. The final review's other minor findings stay deferred, per its triage. Examples: a repeat failure card each day while a failure persists, no log rotation, and Granola and Plaud duplicates suppressed by the prompt only. Cost: polish later.
16. A heading is Markdown heading syntax only, so a tag-first capture such as `#idea buy milk` is still a capture. This corrects ruling 14. Cost: none.
17. After the jobs host's first checks, the sweep's Claude runs with `--restricted --strict-mcp-config --mcp-config <generated file>`. The host's user settings pre-allowed vault plugin tools, which reached the run despite ruling 9. Restricted mode ignores the settings files but also drops user MCP servers, so the sweep writes a temporary config holding only Granola and Plaud (`vault-board mcp-config` prints it). The owner's settings stay unchanged. Cost: if a server's name or URL drifts from the user's own config, its sign-in isn't reused, and the setup check catches it.
18. Granola is read for meetings the owner attended only, so teammates' shared notes aren't scanned. Cost: action items for the owner from a meeting they missed are not drafted.

## Next

- Mac setup (Part A sign-ins, then Part B install, scratch run, go live and schedules), following [jobs/setup.md](jobs/setup.md).
- The phone Shortcut test, end to end.
