import json
from datetime import date
from pathlib import Path

import pytest

from kanban_tui.backends.vault.jobs.sweep_state import (
    StateError,
    SweepState,
    load_state,
    prune,
    save_state,
)


def test_missing_file_loads_empty(tmp_path: Path):
    assert load_state(tmp_path / "state.json") == SweepState()


def test_save_then_load_round_trips_and_creates_folder(tmp_path: Path):
    path = tmp_path / "nested" / "state.json"
    state = SweepState(
        meetings={"m1": "2026-11-01"},
        captures_written={"- a": "01-Projects/A/tasks/a.md"},
        last_success={"granola": "2026-11-03"},
        failure_cards={"Sweep failed": "2026-11-02"},
    )
    save_state(path, state)
    assert load_state(path) == state
    assert json.loads(path.read_text())["version"] == 1
    assert [p.name for p in path.parent.iterdir()] == ["state.json"]


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"meetings": []}',
        '{"meetings": {"m": 3}}',
        '{"captures_written": {"a": null}}',
        '{"version": 1, "last_success": "x"}',
    ],
)
def test_bad_state_raises_and_is_left_alone(tmp_path: Path, content: str):
    path = tmp_path / "state.json"
    path.write_text(content)
    with pytest.raises(StateError):
        load_state(path)
    assert path.read_text() == content


def test_prune_drops_meetings_examined_over_14_days_ago(tmp_path: Path):
    state = SweepState(
        meetings={"old": "2026-10-20", "edge": "2026-10-21", "new": "2026-11-03"},
        captures_written={"- a": "n.md"},
    )
    prune(state, date(2026, 11, 4))
    assert state.meetings == {"edge": "2026-10-21", "new": "2026-11-03"}
    assert state.captures_written == {"- a": "n.md"}
