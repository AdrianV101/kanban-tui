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
