# SDD ledger — plan: docs/vault-board/plans/2026-11-04-board-field.md
Spec: docs/vault-board/design.md. Branch vault-backend. BASE before plan: 1f6edaa. Baseline: 404 passed, mypy 152, ruff clean.

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1-T2 | T1 column_for / fields_for_column / metadata column; T2 consumes all three | consistent |
| T1 self | 1.1 mapping population vs Global Constraints mapping | consistent; old status tests owned by T2 (T1 step 4 notes them) |
| T2 self | with_card_fields(board=None leaves line) vs Done/Archive "leave board untouched" | consistent |
| T2 self | 2.4 replaces old 3.1 status assertion; 2.5 updates 4.1/4.4 | consistent with "change superseded tests, don't keep both" |
| T3 | controller-run: CLAUDE.md rules (wording agreed), push, upgrade, headless check | no subagent |

Ruling: R1 Ledger and tracking docs are committed under docs/vault-board/ (fork-only, cleaned of personal data) so other devices can resume; briefs, reports and diffs stay in the git-ignored workspace — the owner asked to track everything in the fork, and the repo is public — cost if wrong: per-task reports are not visible on other devices.
Task 1: dispatching (BASE 5fad075)
Task 1: ⚠️ resolved by controller: write_task_note skips None-valued keys (checked tests/conftest.py), so the "board absent" cases are real.
Task 1: minor (deferred): write side writes pending/active without board until Task 2 (expected; do not push between tasks)
Task 1: minor (deferred): bare 1/2/3/6 column literals and KNOWN_STATUSES duplicating COLUMN_FIELDS
Task 1: minor (deferred): 1.1 dropped its metadata status assertion (1.3 covers metadata for two notes)
Task 1: complete (commits 5fad075..9bb80b3, review clean)
Task 2: dispatching (BASE 9bb80b3)
Task 2: minor (deferred): conflict refusal says "status changed on disk" even when only board changed — user-visible wording
Task 2: minor (deferred): 2.2 row "board: doing, replaced" overwrites doing with doing (vacuous); ready->doing rows prove replacement
Task 2: complete (commits 9bb80b3..08aa039, review clean)
Final review: dispatching (range 5fad075..08aa039)
Final review: Ready for daily use: Yes. No Critical/Important. Declined item resolved by controller: vault-pkm's frontmatter.js validates enums only for status and priority, and keys against ^[a-zA-Z][a-zA-Z0-9_-]*$, so `board` and `prs` are accepted.
Ruling: R2 One small fix wave for the user-visible conflict wording only (name status and board instead of "status changed"); the other final minors stay deferred per the reviewer's triage (maintainability, vacuous row, case sensitivity, same-column unknown-status overwrite) — cost if wrong: small polish later.
Task 3 (controller): CLAUDE.md rules added; headless check on vault copy: Proposed 58 / Doing 15 / Done 1 / Archive 48, 0 warnings; Ready then In Review move changed only status + one inserted board line; only valid statuses on disk. Final fix 81e9fd4 re-reviewed: ADDRESSED. Plan complete.
