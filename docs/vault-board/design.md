# Kanban board over the vault: design

## Intent

The owner juggles meetings, day-job project work, small bug fixes, product thinking and side projects. The main thread is held by Linear, PRs and the devlog. Small side things have nowhere cheap to land. They stay in memory or in Apple Notes and quietly drop.

Vault task notes exist (236 notes, 70 open on 2026-11-04) but they only flow one way. Notes get written, nothing brings anyone back to look, and the owner's own items drown among Claude's PR follow-ups.

The goal is one kanban-tui board over the vault task notes. It gets opened every morning to plan the day, and again after each finished task to pick the next. Capture has to work from the phone, from meetings and from sessions with Claude, and be faster than Apple Notes.

## Decisions

### The vault is the record

Every card is a vault note with `type: task`. There is no second store of task state. kanban-tui reads and writes the notes directly.

### A vault backend for kanban-tui, in a fork

kanban-tui (Zaloog/kanban-tui, v0.21.2, Python on Textual) stores cards in SQLite. Its backends are a closed set: the `Backends` enum and settings models in `config.py`, and the `match` in `KanbanTui.get_backend()` in `app.py`. A new backend therefore needs a fork. The fork lives under `AdrianV101`, tracks upstream, and is offered upstream once it has proven itself. The sqlite, jira and claude backends stay untouched.

### One board, coloured by project

All work is on one board. Each card's category is its note's `project` (each vault project, plus Personal), each with its own colour. Tasks in `00-Inbox/` with no project count as Personal.

### What the board can do

- **Move cards.** A move sets the note's `status`.
- **Create a card** with a title and a project. It lands in the column it was made in, so a card made in Ready is agreed work. The note follows vault-pkm's conventions: the task template, a kebab-case filename, `01-Projects/<Project>/tasks/` (or `00-Inbox/` for Personal).
- **Open the card's note in Obsidian** with one key. All editing of title, description and other fields happens there.

The board does not edit titles or descriptions, and never rewrites a note body.

### Columns map to `status` and `board`

`status` keeps vault-pkm's four values. The board adds one field of its own, `board`, which vault-pkm does not validate.

| Column | Frontmatter | Notes |
|---|---|---|
| Proposed | `status: pending`, `board` absent or `proposed` | Drafts the owner hasn't agreed to. |
| Ready | `status: pending`, `board: ready` | Agreed, not started. |
| Doing | `status: active`, `board` anything but `in-review` | |
| In Review | `status: active`, `board: in-review` | A PR is open for it. |
| Done | `status: done` | `board` is ignored. |
| Archive | `status: cancelled` | Hidden by default. Rejected proposals land here. `board` is ignored. |

Every task a tool creates is `pending` with no `board` field, so it lands in Proposed without that tool knowing about the board. Moving a card into Proposed, Ready, Doing or In Review writes both `status` and `board` (`proposed`, `ready`, `doing`, `in-review`). Moving into Done or Archive writes only `status`.

### Who moves what

| Move | Who | When |
|---|---|---|
| New card into Proposed | Claude | Morning sweep and session follow-ups |
| Proposed to Ready or Archive | the owner | On the board only |
| Ready to Doing | the owner, or Claude | Claude only when a session starts work on that task |
| Doing to In Review | Claude | When Claude opens the draft PR. It sets `board: in-review` and adds the PR to the note's `prs` list. |
| In Review to Done | Hourly job | When every PR in `prs` is closed and at least one merged into its target branch |
| In Review back to Doing | Hourly job | When every PR in `prs` is closed and none merged. It sets `board: doing`, and a line in the note says so. |
| Anything else to Done | the owner | Always. Claude never marks a non-PR task done. |

Claude never promotes a card out of Proposed.

A task can have several PRs, because stacked and split PRs are common. A new PR attaches to the task the session is working on: the one it tackled or moved to Doing. If the session has no task, a card is created directly in In Review, since the work is already under way. (Claude's calls.)

### Capture sources

- **Phone.** A home-screen iOS Shortcut appends one line to `00-Inbox/Capture.md`. No template, no frontmatter. Obsidian Sync carries it to the Macs.
- **Meetings.** Action items for the owner from Granola notes and Plaud recordings, read through their connectors. The old Plaud audio pipeline stopped writing to the vault on 2026-06-26, so nothing depends on it.
- **Sessions with Claude.** Follow-ups Claude would have written as tasks.

Every draft is a full task note: a title, the project, a line of context, and a link back to where it came from.

### Scheduled jobs run on the Mac mini

The Mac mini is always on. It already runs the Automation daemon under launchd and pm2, with the vault on Obsidian Sync. The owner uses the board on the MacBook. (Claude's call; the owner asked which Mac.)

- **Morning sweep, early each day.** Turns new `Capture.md` lines and new Granola and Plaud action items into Proposed drafts. A line leaves `Capture.md` only after its draft note is written. Reruns never duplicate a draft. If a source fails, the sweep puts a card in Proposed saying which source failed. It never skips silently.
- **Hourly PR check.** For each note in In Review, it reads the state of every PR in `prs` with `gh` and applies the moves in the table above. No model is needed for this job.

The sweep runs as a headless Claude run on the Mac mini with vault-pkm, Granola and Plaud available. If Granola or Plaud can't be made to work there, that source moves to the owner's first session of the day on the MacBook. `Capture.md` handling stays on the Mac mini either way. (Claude's call.)

### No vault-pkm changes

vault-pkm is not changed. Other people use the plugin without a board, and none of this should reach them. The behaviour changes for Claude live in the owner's global `~/.claude/CLAUDE.md`, which overrides skill defaults for the owner only:

- Never set a task note's `status` to `done`. The owner moves cards to Done, except the hourly PR check.
- When starting work on a task in a session, `status: active` is fine (tackle-task already does this).
- When opening a draft PR for a task, set `board: in-review` and add the PR URL to the note's `prs` list. If the session has no task, create one with `status: active`, `board: in-review` and the PR in `prs`.
- When dispatching pkm-capture, pass these rules in the prompt.
- A task the owner himself asks for gets `board: ready`.

The task note gains two optional fields, `board` and `prs` (a list of PR URLs). vault-pkm accepts both because it only validates `status` and `priority`.

### Existing tasks need no migration

The open `pending` tasks have no `board` field, so they show in Proposed as they are, and the `active` ones show in Doing. The owner promotes the ones still real during the first morning pass. Two notes with `status: approved` and `status: superseded` show in Proposed with their original status shown on the card. Moving them writes a valid status.

## Constraints

- There are three writers to the same files: the board and sessions on the MacBook, and the jobs on the Mac mini, all through Obsidian Sync. Writes touch only the frontmatter fields they own. The rest of the note is kept byte for byte.
- A write must not overwrite a newer version of the note. That version may have just arrived through Sync or come from an edit in Obsidian.
- Every status written must be valid under the vault-pkm task enum (`pending`, `active`, `done`, `cancelled`). vault-pkm itself is never changed.
- External edits show up on the board's existing refresh (the `r` key and the auto-refresh timer).
- The board never deletes a note file.

## Goals and non-goals

Goals:

- Capture from anywhere in seconds.
- One morning view of all work.
- Claude's drafts are kept apart from agreed work.
- In-flight PRs are visible, and they finish themselves on merge.

Non-goals (Claude's call unless noted):

- Linear issues are not mirrored to the board. Linear stays the team tracker.
- There is no board on the phone. The phone only captures.
- Apple Notes is not integrated.
- Task dependencies are not supported in the vault backend at first.
- kanban-tui's own CLI and MCP don't need to work against the vault backend. Claude writes through vault-pkm.
- Anti-goals are deferred at the owner's request.

## Build order

1. Vault backend in the kanban-tui fork, reworked to map columns from `status` and `board`.
2. The local rules in the owner's global `~/.claude/CLAUDE.md`.
3. Scheduled jobs on the Mac mini.
4. Phone Shortcut.

Each part gets its own plan.

## Left to the builder

- How a note maps to kanban-tui's integer task id, stably across renames and moves.
- Where a card's position within a column is stored.
- Which note parts are shown as the card's title and description.
- Whether kanban-tui's start and finish dates map to frontmatter fields.
- What happens to a card deleted on the board. It must not delete the file.
- How long Done cards stay visible before they drop off the board.
- launchd or pm2 for the jobs, sweep timing, and catch-up after the Mac mini sleeps.
- How the sweep remembers what it has processed, and how it de-duplicates.
- Shortcut mechanics, for example an Obsidian URI that appends to a note.
- Checking the Mac mini has the Granola and Plaud connectors and `gh` signed in to both GitHub accounts.
