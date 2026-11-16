# Vault board

A kanban-tui backend that shows an Obsidian vault's task notes as one board, plus the plans and progress for the wider workflow around it. This folder is fork-only: drop it before offering the backend upstream.

- [design.md](design.md): the approved design.
- [plans/](plans/): one implementation plan per piece of work.
- [progress.md](progress.md): what's done, what's next, and every ruling made during execution.
- `ledger-*.md`: the execution ledger of the plan in progress. A session on another device resumes from it.

## Status

| Part | What | State |
|---|---|---|
| 1 | Vault backend in this fork ([plan](plans/2026-11-04-vault-backend.md)) | Done. Draft PR #1. |
| 1b | Columns from `status` plus a `board` field ([plan](plans/2026-11-04-board-field.md)) | Done |
| 2 | Board rules for Claude in the owner's global `~/.claude/CLAUDE.md` | Done |
| 3 | Morning capture sweep and hourly PR merge check on the Mac mini ([plan](plans/2026-11-04-mac-mini-jobs.md)) | Code done; Mac setup in progress |
| 4 | Phone capture Shortcut | How-to written ([jobs/phone-shortcut.md](jobs/phone-shortcut.md)); phone setup pending |

## Scheduled jobs

`vault-board pr-check` (hourly) and `vault-board sweep` (daily at 06:30) run under launchd on an always-on Mac. Follow [jobs/setup.md](jobs/setup.md) to install them.

## Install on a device

```bash
uv tool install "kanban-tui[vault] @ git+https://github.com/AdrianV101/kanban-tui@vault-backend"
uv tool upgrade kanban-tui   # pick up new commits on the branch later
```

Then set the backend in `~/.config/kanban_tui/config.toml` (`ktui info` shows the path):

```toml
[backend]
mode = "vault"

[backend.vault_settings]
vault_path = "<vault>"

[board]
auto_refresh_interval = 60
```

## Start a Claude Code session from a card

Press `t` on a card in Proposed, Ready or Doing. The board opens a kitty tab in the background that runs `claude "/vault-pkm:tackle-task <note path>"`. The tab is titled with the task.

The tab starts in this device's checkout of the project's repo. The board reads the remotes in `repos:` of the project's `_index.md` (vault-pkm v4's link). It then looks for a main git checkout with one of those remotes directly under `checkouts_root`. When nothing matches, or several checkouts match, the board shows an error and starts nothing. A project with no `repos:`, and an inbox task with no project, get a question asking which folder to start in.

```toml
[backend.vault_settings]
checkouts_root = "~/Projects"   # the default
```

Run the board in kitty, with remote control on. Add these lines to `~/.config/kitty/kitty.conf`, then restart kitty:

```
allow_remote_control socket-only
listen_on unix:/tmp/kitty
```

## Work on it from a device

```bash
git clone https://github.com/AdrianV101/kanban-tui.git && cd kanban-tui
git switch vault-backend
uv sync --all-extras
make test
```

Read [progress.md](progress.md) first, then the open plan and its ledger.
