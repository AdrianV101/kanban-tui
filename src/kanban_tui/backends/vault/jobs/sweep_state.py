from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

STATE_VERSION = 1
MEETING_KEEP_DAYS = 14
_MAPS = ("meetings", "captures_written", "last_success", "failure_cards")


class StateError(Exception):
    """The state file exists but cannot be trusted."""


@dataclass
class SweepState:
    meetings: dict[str, str] = field(default_factory=dict)
    captures_written: dict[str, str] = field(default_factory=dict)
    last_success: dict[str, str] = field(default_factory=dict)
    failure_cards: dict[str, str] = field(default_factory=dict)


def load_state(path: Path) -> SweepState:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return SweepState()
    except (OSError, UnicodeDecodeError) as error:
        raise StateError(f"cannot read {path} ({error})") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StateError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise StateError(f"{path} must hold a JSON object")
    maps: dict[str, dict[str, str]] = {}
    for name in _MAPS:
        value = data.get(name, {})
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            raise StateError(f"{path}: '{name}' must map strings to strings")
        maps[name] = value
    return SweepState(**maps)


def save_state(path: Path, state: SweepState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": STATE_VERSION} | {
        name: getattr(state, name) for name in _MAPS
    }
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def prune(state: SweepState, today: date) -> None:
    """Drop meetings examined more than 14 days ago; unparseable dates are kept."""
    cutoff = today - timedelta(days=MEETING_KEEP_DAYS)

    def is_stale(examined: str) -> bool:
        try:
            return date.fromisoformat(examined) < cutoff
        except ValueError:
            return False

    state.meetings = {k: v for k, v in state.meetings.items() if not is_stale(v)}
