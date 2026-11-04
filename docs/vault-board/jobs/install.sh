#!/usr/bin/env bash
# Installs the vault-board launchd jobs for the current user. Rerun after a
# Node upgrade so the jobs see the new Node folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
labels=(com.vault-board.pr-check com.vault-board.sweep)
config="$HOME/.config/vault-board/jobs.toml"

vault_board="$(command -v vault-board || true)"
if [ -z "$vault_board" ]; then
    echo "vault-board is not on PATH. Run: uv tool install --force \"kanban-tui[vault] @ git+https://github.com/AdrianV101/kanban-tui@vault-backend\"" >&2
    exit 1
fi
if [ ! -f "$config" ]; then
    echo "Missing $config. Copy $here/jobs.example.toml there and fill it in." >&2
    exit 1
fi
node="$(command -v node || true)"
if [ -z "$node" ]; then
    echo "node is not on PATH. The sweep needs it for the Granola and Plaud servers." >&2
    exit 1
fi
node_bin="$(dirname "$node")"

mkdir -p "$HOME/Library/Logs" "$HOME/Library/LaunchAgents"

for label in "${labels[@]}"; do
    plist="$HOME/Library/LaunchAgents/$label.plist"
    sed -e "s|__HOME__|$HOME|g" \
        -e "s|__NODE_BIN__|$node_bin|g" \
        -e "s|__VAULT_BOARD__|$vault_board|g" \
        "$here/$label.plist.template" > "$plist"
    plutil -lint "$plist"
    launchctl bootout "gui/$UID" "$plist" 2>/dev/null || true
    launchctl bootstrap "gui/$UID" "$plist"
    echo "Installed $label ($plist)"
done

echo "vault-board: $vault_board"
echo "Node folder: $node_bin"
echo "Logs: $HOME/Library/Logs/vault-board-pr-check.log and vault-board-sweep.log"
