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
| 3 | Morning capture sweep and hourly PR merge check on the Mac mini | Not started |
| 4 | Phone capture Shortcut | Not started |

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

## Work on it from a device

```bash
git clone https://github.com/AdrianV101/kanban-tui.git && cd kanban-tui
git switch vault-backend
uv sync --all-extras
make test
```

Read [progress.md](progress.md) first, then the open plan and its ledger.
