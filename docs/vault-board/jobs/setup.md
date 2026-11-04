# Mac setup for the scheduled jobs

Set up an always-on Mac to run `vault-board pr-check` (hourly) and `vault-board sweep` (daily at 06:30) under launchd. Run the steps in order. Stop and report if a check fails.

The Mac needs the Obsidian vault folder synced locally, `uv`, Node (for `npx`), the GitHub CLI (`gh`) and Claude Code (`claude`).

## Part A: accounts and tools (before the install)

0. Get the repo. Every repo path below (`docs/...`, `src/...`) is relative to this checkout.

   ```bash
   mkdir -p ~/Projects
   [ -d ~/Projects/kanban-tui ] || git clone https://github.com/AdrianV101/kanban-tui.git ~/Projects/kanban-tui
   cd ~/Projects/kanban-tui && git switch vault-backend && git pull
   ```

1. Sign the GitHub CLI in to every account the PRs need.
   - Run `gh auth login` once per account.
   - Run `gh auth switch` to put git's usual account back as the active one.
   - Run `gh auth status` and check each account is listed.
2. Add the Granola server at user scope, then restart Claude Code and authenticate through `/mcp`:

   ```bash
   claude mcp add -s user granola --transport http https://mcp.granola.ai/mcp
   ```

3. Add the Plaud server at user scope, then run its `login` tool in Claude Code:

   ```bash
   claude mcp add -s user plaud -- "$(command -v npx)" -y @plaud-ai/mcp@latest
   ```

4. Check headless access. This uses the same restriction flags as the sweep. Replace `<list>` with the comma-separated tool names in `ALLOWED_TOOLS` in `src/kanban_tui/backends/vault/jobs/sweep_agent.py`:

   ```bash
   claude -p "List my three most recent Granola meetings and my three most recent Plaud files by title." --restricted --tools "" --permission-mode dontAsk --allowedTools "<list>"
   ```

   The reply must show titles from both. If it reports a tool as denied or missing, run `claude mcp list`, find the real tool names the two servers expose, and correct `ALLOWED_TOOLS` in `sweep_agent.py` (and its test) to match.
5. Check that the run sees only Granola and Plaud. `--restricted` ignores the user, project and local settings files, so their allow rules and the plugins they enable don't reach the sweep. Run the same flags with this prompt: "List every tool you have whose name starts with mcp__, one per line, nothing else." The list must hold only `mcp__granola__` and `mcp__plaud__` tools. If any other MCP tool appears (for example a vault plugin's), stop and tell the owner: the sweep must not run until it's gone. Leave `~/.claude/settings.json` as it is; the owner's other sessions rely on it.

## Part B: install and run

1. Install the command:

   ```bash
   uv tool install --force "kanban-tui[vault] @ git+https://github.com/AdrianV101/kanban-tui@vault-backend"
   ```

2. Write the config. Copy `docs/vault-board/jobs/jobs.example.toml` to `~/.config/vault-board/jobs.toml` and fill in the vault path, the owner's name, and one `gh_accounts` line per PR owner. Ask the owner for these values.
3. Make a scratch copy of the vault's task notes:
   - `01-Projects/*/tasks/`
   - `00-Inbox/*.md`
   - `05-Templates/task.md`

   Write a second config for it with that scratch `vault_path` and its own `state_path`, for example a file next to the scratch folder.
4. Run both commands against the scratch copy:

   ```bash
   vault-board pr-check --config <scratch config>
   vault-board sweep --config <scratch config>
   ```

   Each prints a start line, one line per action and a summary. Exit code 0 means success, 1 means a PR could not be read or the sweep had errors, 2 means a config problem.
5. Open the drafts the sweep created in the scratch copy. Check each has a sensible title, project and link. Show the owner anything odd.
6. Run both commands against the real vault with the real config (no `--config`).
7. Install the schedules:

   ```bash
   docs/vault-board/jobs/install.sh
   ```

   It fills the plist templates, copies them to `~/Library/LaunchAgents`, and loads them. Both jobs run at load, so installing (and every login) triggers a PR check and a sweep, and each sweep is one Claude run.
8. Check the jobs loaded and ran:

   ```bash
   launchctl print gui/$UID/com.vault-board.pr-check
   launchctl print gui/$UID/com.vault-board.sweep
   cat ~/Library/Logs/vault-board-pr-check.log ~/Library/Logs/vault-board-sweep.log
   ```

   Each log starts every run with a `<command> started <time>` line.

   Then run each job once by hand through launchd and read its log:

   ```bash
   launchctl kickstart -k gui/$UID/com.vault-board.pr-check
   launchctl kickstart -k gui/$UID/com.vault-board.sweep
   cat ~/Library/Logs/vault-board-pr-check.log ~/Library/Logs/vault-board-sweep.log
   ```

   Each log must show a `started` line and a summary line for the new run.

   A vault under `~/Documents` is a protected folder. The first run under launchd may raise a macOS prompt asking to allow access to the Documents folder. Approve it at the Mac or over Screen Sharing. If a log shows "Operation not permitted", grant Full Disk Access (System Settings, Privacy & Security) to the Python interpreter `vault-board` runs on. `head -1 "$(command -v vault-board)"` shows its path.

   LaunchAgents and the Claude login only exist in a logged-in session. Keep the Mac logged in to its desktop session, and do not let it sleep through 06:30.
9. After a Node upgrade, rerun `docs/vault-board/jobs/install.sh` so the jobs pick up the new Node folder.
