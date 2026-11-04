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

## Part 1b: board field (in progress)

Plan: [plans/2026-11-04-board-field.md](plans/2026-11-04-board-field.md). The ledger is in `ledger-board-field.md`.
