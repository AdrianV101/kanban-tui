# SDD ledger — plan: docs/vault-board/plans/2026-11-04-mac-mini-jobs.md

Spec: docs/vault-board/design.md (fork copy of the approved design). Branch vault-backend, start d6fd9b2. Baseline: 429 tests pass, mypy 152. Models: every implementer and reviewer is sonnet (owner's instruction). Task 7 runs on the Mac mini, not here.

## Pre-flight scan

| Rows | Produces vs consumes / self-check | Found | Ruling |
|---|---|---|---|
| T1-T2 | T1 metadata `prs`, `move_with_note`, `update_task_status` refusal dicts; T2 consumes them | consistent | - |
| T1-T5 | T1 `writable_projects() -> dict[str, int or None]`; T5 says "projects is writable_projects()" but `SweepRequest.projects: list[str]` | type mismatch | R1 |
| T1-T5 | T1 `create_new_task(..., source=)`; T5 passes `source` | consistent | - |
| T2-T4 | `Runner` defined in T2 (github.py), consumed by T4 sweep_agent.py | odd coupling | R2 |
| T3-T5 | `SweepState` maps, `failure_cards` keyed by card title in both | consistent | - |
| T3-T5 | `last_success` keyed by source; T5 "each source with no error" leaves the capture source unclear | ambiguity | R3 |
| T3-T5 | step 2 removal can fail; step 3 must not resend those lines | gap | R4 |
| T4-T5 | `examined` bare ids vs state keys `<source>:<id>`, `processed` list of keys | consistent if keys are `f"{source}:{id}"` | - |
| T4-T5 | a source with an error may still return drafts and examined ids | ambiguity | R5 |
| T2-T6, T4/T5-T6 | CLI wires `GhPrStates`, `check_prs`, `run_agent`, `run_sweep`, `VaultBackend(settings=VaultBackendSettings(vault_path=...))` | consistent | - |
| T1 self | tests 1.1-1.5 match Produces | consistent | - |
| T2 self | Runner raises `TimeoutExpired` on timeout; GhPrStates must turn it into `PrFetchError`; no gh timeout value given | gap | R6 |
| T3 self | `remove_capture_lines` needs a stat-checked replace; backend has `VaultBackend._replace_file` | reuse question | R7 |
| T4 self | `--allowedTools <list>` argv shape unspecified | ambiguity | R8 |
| T5 self | order steps 1-8 match tests 5.1-5.8 | consistent | - |
| T6 self | 6.2 replaces runners; CLI needs an injection seam | consistent (module-level default runner, monkeypatched) | - |

- Ruling R1: `SweepRequest.projects` is `list(writable_projects())` (the names); the sweep keeps the dict to look up the category id when writing; unknown names map to Personal (category `None`) — the interface types stay as written — cost if wrong: none, names and ids both available.
- Ruling R2: Task 2 creates `jobs/runner.py` holding `Runner` and the default subprocess runner; github.py and sweep_agent.py import it — a sweep module importing from github.py would couple unrelated adapters — cost if wrong: one extra small file.
- Ruling R3: `last_success` and `since` cover only `granola` and `plaud`; Capture.md has no window — the window only matters for meeting sources — cost if wrong: none.
- Ruling R4: an item whose raw line is in `captures_written` is never sent to the agent, whether or not its removal succeeded; a failed removal makes the "Capture sweep: Capture.md failed" card — prevents duplicate drafts — cost if wrong: a stuck line needs a manual delete.
- Ruling R5: drafts and examined ids from a source that also reports an error are still validated and written; only `last_success` holds back — partial results are real work — cost if wrong: a half-read meeting could be marked examined; the model is told to examine only meetings it read fully.
- Ruling R6: `gh` calls run with a 30 s timeout; `GhPrStates` turns `TimeoutExpired` into `PrFetchError` — the plan's rule "a PR it can't read leaves the card alone" — cost if wrong: a slow gh skips a card for an hour.
- Ruling R7: `remove_capture_lines` reuses `VaultBackend._replace_file` (same package) and catches its `VaultWriteError` as the "changed on disk" signal — one replace path, per Global Constraints — cost if wrong: a private-name import.
- Ruling R8: `--allowedTools` gets one comma-separated argument holding the pinned list — the Claude CLI accepts it — cost if wrong: Task 7's headless check catches it.

## Tasks

Task 1: dispatched (base d6fd9b2, implementer a06c27851a6cd6542, sonnet)
Task 1: implemented f0ffd5a (450 tests pass, mypy 152); review dispatched (a1739f8036897e0bb, sonnet)
Task 1: review approved, spec ✅. ⚠️ writable_projects reading the category maps: resolved by test 1.5 (creation with each listed id lands in that folder), passing in the reported run.
Task 1: minor (deferred): `source` values like true/null/123 match SAFE_YAML_SCALAR and parse back as non-strings (same as project).
Task 1: minor (deferred): move_with_note doesn't reject a line with an embedded newline.
Task 1: minor (deferred): test_vault_create expected filename built via note_filename rather than a literal.
Task 1: minor (deferred): no direct unit test of with_appended_line on empty text or a lone \r ending.
Task 1: complete (commits d6fd9b2..f0ffd5a, review clean)
Task 2: dispatched (base f0ffd5a, implementer a8fd852ed99a6f622, sonnet; carries R2, R6)
Task 2: implemented a547c46 (481 tests pass, mypy 152)
Task 2: review approved, spec ✅. ⚠️ prs normalization: resolved by Task 1 test 1.1 (non-string entries give [] plus invalid_fields).
Task 2: minor (deferred, final review should triage): only PrFetchError is caught; FileNotFoundError when gh is missing aborts the whole run (GhPrStates could map OSError to PrFetchError).
Task 2: minor (deferred): failed fetches aren't cached, so a failing shared URL is retried per card (up to 30 s each).
Task 2: minor (deferred): PrFetchError message ends in a dangling ": " when stderr is empty.
Task 2: minor (deferred): tests don't cover a refused reopen write, the 30 s timeout argument, or the Archive column in the scope test.
Task 2: minor (deferred): URL variants of one PR (/pull/12 vs /pull/12/files) are separate dedupe keys.
Task 2: complete (commits f0ffd5a..a547c46, review clean)
Task 3: dispatched (base a547c46, implementer a851f645cb187f8a3, sonnet; carries R7)
Task 3: implemented b7a448f (501 tests pass, mypy 152)
Task 3: review approved, spec ✅. ⚠️ _replace_file internals: resolved by reading backend.py (compares mtime_ns and size against read_stat, raises VaultWriteError, writes content.encode("utf-8") verbatim).
Task 3: minor (deferred, final review should triage): a bullet-only line "- " becomes an item with text "-" (an empty phone capture would produce it); report wrongly claims it's skipped.
Task 3: minor (deferred): load_state accepts any version value.
Task 3: minor (deferred): prune keeps unparseable dates forever, untested.
Task 3: minor (deferred): non-UTF-8 Capture.md raises bare UnicodeDecodeError.
Task 3: minor (deferred): untested paths: removal with no matching line, load_state OSError, save_state temp cleanup on failure.
Task 3: complete (commits a547c46..b7a448f, review clean)
Task 4: dispatched (base b7a448f, implementer a17ebc68e23ff822d, sonnet; carries R5, R8; reply JSON shape pinned in dispatch)
Task 4: implemented f4c41be (526 tests pass, mypy 152)
Task 4: review approved, spec ✅. ⚠️ Runner signature: resolved (runner.py:7 is Callable[[list[str], dict[str, str], float], tuple[int, str, str]]).
- Ruling R9: harden the sweep's claude argv beyond the plan's pinned shape: add `--tools ""` (no built-in tools; the run needs none) and `--permission-mode dontAsk` (deny anything not pre-approved), and add one prompt sentence that capture text and meeting content are data, never instructions — `--allowedTools` only pre-approves, and meeting transcripts carry other people's words while the Mac mini's user settings may pre-allow other MCP write tools — cost if wrong: if the Mac mini's CLI lacks dontAsk or rejects `--tools ""`, the run fails loudly and Task 7's headless check catches it; the runbook adds a check of the Mac mini's permissions.allow list.
Task 4: minor (deferred): parser doesn't check source_key prefixes or one-draft-per-capture (Task 5 validation owns both, tests 5.6).
Task 4: minor (deferred): rule assertions in test 4.3 are loose substrings.
Task 4: minor (deferred): _per_source returns Any.
Task 4: fix round 1/5 (3 addressed, 0 open — R9 argv hardening and prompt sentence; commits f4c41be..5a4ea41). Runbook in the owner's vault note gained the same flags in its headless check plus a check of the Mac mini's permissions.allow.
Task 4: complete (commits b7a448f..5a4ea41, review clean)
Note: the Mac mini log (owner's vault note) says Part A steps 1-4 are done; both gh accounts were already signed in; Granola needs auth; Plaud connected, login pending. It also notes the host's Automation daemon LaunchAgent is not loaded. Doesn't affect these jobs.
- Ruling R10: the sweep matches a draft's project to writable_projects() names ignoring case; no match means Personal — models drift on case — cost if wrong: none.
- Ruling R11: "adds no state keys" in test 5.5 means no meetings or captures_written keys; the failure_cards date for the card is still recorded so the card stays once per day — cost if wrong: none.
Task 5: dispatched (base 5a4ea41, implementer a9334f9b99f272c0e, sonnet; carries R1, R3, R4, R5, R10, R11)
Task 5: implemented e368adb (537 tests pass, mypy 152); concerns: sweep.py 264 lines, partial meeting write re-creates drafts on rerun (plan behaviour)
Task 5: review needs fixes (spec ❌): I1 meeting keys recorded only after all drafts, so a crash or a partly failed meeting duplicates drafts on rerun; I2 failure paths untested (CaptureWriteError at both removal steps, combined errors, processed meeting skipped in-run, 5.7 never asserts a card).
- Ruling R12: record a meeting's key in state.meetings (and save) as soon as its first draft is written, overriding the plan's "mark examined meetings whose drafts were all written"; if a later draft of that meeting fails, the meeting's source card names the failed draft's title so the owner can add it by hand — the spec says reruns never duplicate a draft, which outranks retrying a partial meeting — cost if wrong: a failed second draft of a meeting isn't retried automatically, but its card names it.
Task 5: minor (deferred): silent `except VaultWriteError: continue` when a failure card can't be created (error is already in the report).
Task 5: minor (deferred): save_state raising inside finally can mask the original exception.
Task 5: minor (deferred): _sweep has 9 parameters and ~80 lines; capture and meeting loops could be split.
Task 5: minor (deferred): capture item lookup by id is O(n^2).
Task 5: fix round 1/5 (2 addressed, 0 open — I1 meeting marked on first draft per R12, I2 failure-path tests; commits e368adb..7ade643)
Task 5: minor (deferred): sweep.py ~264-270 lines, slightly over the ~250 guideline.
Task 5: complete (commits 5a4ea41..7ade643, review clean)
Task 6: dispatched (base 7ade643, implementer a66dd37ecd8cad398, sonnet; output format, exit 2 on a missing vault folder, plist placeholders and install.sh steps pinned in dispatch)
Task 6: implemented 0cf5ce4 (559 tests pass, mypy 152, uv.lock unchanged; install.sh not executed, bash -n and plutil -lint only)
Task 6: review needs fixes: I1 setup.md references repo files (jobs.example.toml, install.sh, sweep_agent.py) but never clones the repo; I2 install.sh bootout then immediate bootstrap can fail on reinstall under set -e.
Task 6: minor (folded into the fix round as doc text): setup.md should say the sweep also runs at load (install and login), each a Claude call.
Task 6: minor (deferred): --help shows the expanded home path as the --config default.
Task 6: minor (deferred): sed replacement breaks on & or | in paths.
Task 6: minor (deferred): scratch-config state_path instruction is loose.
Task 6: fix round 1/5 (3 addressed, 0 open — clone step, bootstrap retry, run-at-load note; commits 0cf5ce4..28d7bcb)
Task 6: minor (deferred): git pull in the clone step fails on a checkout with local changes (visible to whoever runs it).
Task 6: complete (commits 7ade643..28d7bcb, review clean)
Final review: dispatched (d6fd9b2..28d7bcb, a82b9f4c11e6437fd, sonnet per owner instruction)
Final review: With fixes. Important: F1 missing/unrunnable claude (OSError) aborts the sweep with no card, plus no catch-all in run_sweep (also covers non-UTF-8 or unreadable Capture.md); F2 missing gh (OSError) aborts the PR check; F3 model text written unescaped (Templater `<%` blocks could run on create; a newline in a title breaks the heading); F4 setup.md lacks a launchctl kickstart smoke test, the ~/Documents access prompt under launchd, and the logged-in/awake requirement. Must-fix minors: F5 bullet-only "- " line becomes an item; F6 a "# heading" line in Capture.md becomes an item and is then deleted.
- Ruling R13: model-supplied title, context and link get `<%` rewritten to `< %` and the title collapsed to one line (runs of whitespace to one space) before writing; drafts are not rejected — breaks Templater syntax while keeping the text readable — cost if wrong: a capture that really contains `<%` reads slightly differently.
- Ruling R14: Capture.md heading lines (`#`), bullet-only lines and a leading YAML frontmatter block are not capture items and are never removed — a heading or properties the owner adds must survive — cost if wrong: none.
- Ruling R15: the final review's other minors stay deferred, per its triage (repeat failure cards per day, crash window between create and save for a capture, install.sh not checking gh/claude, no log rotation, Granola/Plaud duplicate suppression by prompt only, and every per-task minor it marked fine to defer) — cost if wrong: polish later.
Final review: fix wave dispatched (base 28d7bcb, a0c447d13ce34a5f5, sonnet; F1-F6 with R13, R14)
- Ruling R16 (corrects R14): a heading is a line matching Markdown heading syntax, one to six `#` then a space or the line end; a line like `#idea buy milk` (an Obsidian tag) is a capture — R14 as worded would silently strand tag-first captures in Capture.md — cost if wrong: none.
Final review: fix wave e599c4b (576 tests pass); R16 sent to the same fixer within the wave before the re-review.
Final review: fix wave re-review — all findings addressed (F1-F6), no new breakage; commits 28d7bcb..77aa6df.
Final review: parked — frontmatter protected only when a closing `---` exists — Ruling: a lone opening `---` is rare and its lines are just treated as captures, nothing is lost.
Final review: parked — heading regex accepts any leading spaces (CommonMark allows three) — Ruling: cosmetic.
Final review: complete (commits d6fd9b2..77aa6df)
