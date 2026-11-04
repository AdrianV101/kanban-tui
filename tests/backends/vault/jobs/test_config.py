from pathlib import Path

import pytest

from kanban_tui.backends.vault.jobs.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    load_config,
)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "jobs.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_names_the_path_and_the_example(tmp_path: Path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(ConfigError) as error:
        load_config(missing)
    assert str(missing) in str(error.value)
    assert "jobs.example.toml" in str(error.value)


@pytest.mark.parametrize(
    "text",
    [
        'owner_name = "Alex"\n',
        'vault_path = "~/v"\n',
        'vault_path = "~/v"\nowner_name = "Alex"\ngh_accounts = "x"\n',
        'vault_path = 3\nowner_name = "Alex"\n',
        'vault_path = "~/v"\nowner_name = "Alex"\n[gh_accounts]\norg = 1\n',
        "vault_path = \n",
    ],
)
def test_invalid_config_raises(tmp_path: Path, text: str):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_defaults_and_home_expansion(tmp_path: Path):
    config = load_config(write(tmp_path, 'vault_path = "~/v"\nowner_name = "Alex"\n'))
    home = Path.home()
    assert config.vault_path == home / "v"
    assert config.gh_accounts == {}
    assert config.claude_path == home / ".local/bin/claude"
    assert config.sweep_model == "sonnet"
    assert config.state_path == home / ".local/state/vault-board/sweep.json"


def test_explicit_values_override_defaults(tmp_path: Path):
    text = (
        'vault_path = "/v"\nowner_name = "Alex"\nclaude_path = "~/c"\n'
        'sweep_model = "opus"\nstate_path = "~/s.json"\n'
        '[gh_accounts]\n"example-org" = "work"\n'
    )
    config = load_config(write(tmp_path, text))
    assert config.gh_accounts == {"example-org": "work"}
    assert config.claude_path == Path.home() / "c"
    assert config.sweep_model == "opus"
    assert config.state_path == Path.home() / "s.json"


def test_default_config_path():
    assert DEFAULT_CONFIG_PATH == Path.home() / ".config/vault-board/jobs.toml"
