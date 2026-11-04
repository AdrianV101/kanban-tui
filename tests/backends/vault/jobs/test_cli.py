import subprocess
from pathlib import Path

from click.testing import CliRunner

from kanban_tui.backends.vault.jobs import cli
from kanban_tui.backends.vault.jobs.cli import main
from tests.conftest import write_task_note

CAPTURE = "00-Inbox/Capture.md"


def make_config(tmp_path: Path, vault: Path) -> Path:
    path = tmp_path / "jobs.toml"
    path.write_text(
        f'vault_path = "{vault}"\nowner_name = "Alex"\n'
        f'claude_path = "{tmp_path / "claude"}"\n'
        f'state_path = "{tmp_path / "state" / "sweep.json"}"\n',
        encoding="utf-8",
    )
    return path


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def test_pr_check_with_nothing_in_review(test_vault: Path, tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def run(argv, env, timeout):
        calls.append(argv)
        return 0, "", ""

    monkeypatch.setattr(cli, "run_command", run)
    write_task_note(test_vault, "01-Projects/Alpha/tasks/a.md", {"status": "active"})
    result = invoke(["pr-check", "--config", str(make_config(tmp_path, test_vault))])
    lines = result.output.splitlines()
    assert result.exit_code == 0, result.output
    assert lines[0].startswith("pr-check started 20")
    assert lines[-1] == "pr-check: 0 done, 0 back to Doing, 0 skipped"
    assert calls == []


def test_pr_check_reports_actions_and_skips(
    test_vault: Path, tmp_path: Path, monkeypatch
):
    def run(argv, env, timeout):
        if argv[:2] == ["gh", "auth"]:
            return 1, "", "no account"
        return 0, '{"state": "MERGED"}', ""

    monkeypatch.setattr(cli, "run_command", run)
    note = "01-Projects/Alpha/tasks/a.md"
    write_task_note(
        test_vault,
        note,
        {
            "status": "active",
            "board": "in-review",
            "prs": "\n  - https://github.com/o/r/pull/1",
        },
    )
    result = invoke(["pr-check", "--config", str(make_config(tmp_path, test_vault))])
    assert result.exit_code == 0, result.output
    assert f"done: {note}" in result.output
    assert result.output.splitlines()[-1] == (
        "pr-check: 1 done, 0 back to Doing, 0 skipped"
    )


def test_sweep_agent_error_exits_one(test_vault: Path, tmp_path: Path, monkeypatch):
    def run(argv, env, timeout):
        return 1, "", "boom"

    monkeypatch.setattr(cli, "run_command", run)
    result = invoke(["sweep", "--config", str(make_config(tmp_path, test_vault))])
    lines = result.output.splitlines()
    assert result.exit_code == 1, result.output
    assert lines[0].startswith("sweep started 20")
    assert any(line.startswith("error: Capture sweep failed: ") for line in lines)
    assert lines[-1] == "sweep: 0 drafts, 1 errors"


def test_sweep_timeout_is_an_error_not_a_crash(
    test_vault: Path, tmp_path: Path, monkeypatch
):
    def run(argv, env, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(cli, "run_command", run)
    result = invoke(["sweep", "--config", str(make_config(tmp_path, test_vault))])
    assert result.exit_code == 1, result.output


def test_bad_config_exits_two_on_stderr(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["pr-check", "--config", str(tmp_path / "nope.toml")])
    assert result.exit_code == 2
    assert "nope.toml" in result.stderr
    assert result.stdout == ""


def test_missing_vault_folder_exits_two(tmp_path: Path):
    config = make_config(tmp_path, tmp_path / "no-vault")
    result = CliRunner().invoke(main, ["sweep", "--config", str(config)])
    assert result.exit_code == 2
    assert "no-vault" in result.stderr
