from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/.config/vault-board/jobs.toml").expanduser()
EXAMPLE_NAME = "docs/vault-board/jobs/jobs.example.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class JobsConfig:
    vault_path: Path
    owner_name: str
    gh_accounts: dict[str, str]
    claude_path: Path
    sweep_model: str
    state_path: Path


def _text(data: dict[str, Any], key: str, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key!r} must be a non-empty string")
    return value


def load_config(path: Path) -> JobsConfig:
    """Read the jobs config. Raises ConfigError for a missing or invalid file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(
            f"Config file not found: {path}. Copy {EXAMPLE_NAME} there and fill it in."
        ) from None
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Cannot read {path}: {error}") from None
    try:
        accounts = data.get("gh_accounts", {})
        if not isinstance(accounts, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in accounts.items()
        ):
            raise ConfigError("'gh_accounts' must be a table of owner = account text")
        return JobsConfig(
            vault_path=Path(_text(data, "vault_path")).expanduser(),
            owner_name=_text(data, "owner_name"),
            gh_accounts=dict(accounts),
            claude_path=Path(
                _text(data, "claude_path", "~/.local/bin/claude")
            ).expanduser(),
            sweep_model=_text(data, "sweep_model", "sonnet"),
            state_path=Path(
                _text(data, "state_path", "~/.local/state/vault-board/sweep.json")
            ).expanduser(),
        )
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from None
