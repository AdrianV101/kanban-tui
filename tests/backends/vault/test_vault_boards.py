from pathlib import Path

import pytest

from kanban_tui.backends.vault.backend import VaultBackend
from kanban_tui.config import VaultBackendSettings, VaultBoard
from tests.conftest import write_task_note

BOARDS = [
    VaultBoard(name="Work", projects=["acme"]),
    VaultBoard(name="Personal", exclude_projects=["ACME"]),
    VaultBoard(name="Everything"),
    VaultBoard(name="Inbox", projects=["personal"]),
]
CARDS = {
    "acme-card": "01-Projects/Acme/tasks/acme-card.md",
    "alpha-card": "01-Projects/Alpha/tasks/alpha-card.md",
    "inbox-card": "00-Inbox/inbox-card.md",
    "loose-card": "Notes/loose-card.md",
}
GLOBS = ["01-Projects/*/tasks/*.md", "00-Inbox/*.md", "Notes/*.md"]


@pytest.fixture
def board_vault(test_vault: Path) -> Path:
    for rel_path in CARDS.values():
        write_task_note(test_vault, rel_path)
    return test_vault


def make_backend(vault: Path, active_board: str = "") -> VaultBackend:
    return VaultBackend(
        VaultBackendSettings(
            vault_path=vault.as_posix(),
            task_globs=GLOBS,
            boards=BOARDS,
            active_board=active_board,
        )
    )


def titles(backend: VaultBackend) -> set[str]:
    return {task.title for task in backend.get_tasks_on_active_board()}


def test_boards_list_all_cards_first_then_the_configured_boards_in_order(
    board_vault: Path,
):
    boards = make_backend(board_vault).get_boards()

    assert [(board.board_id, board.name) for board in boards] == [
        (1, "Vault"),
        (2, "Work"),
        (3, "Personal"),
        (4, "Everything"),
        (5, "Inbox"),
    ]


@pytest.mark.parametrize(
    "board,shown",
    [
        ("Work", {"acme-card"}),
        ("Personal", {"alpha-card", "inbox-card", "loose-card"}),
        ("Everything", set(CARDS)),
        ("Inbox", {"inbox-card", "loose-card"}),
    ],
)
def test_a_board_shows_exactly_the_cards_its_projects_rule_allows(
    board_vault: Path, board: str, shown: set[str]
):
    backend = make_backend(board_vault)
    board_id = next(b.board_id for b in backend.get_boards() if b.name == board)

    assert {task.title for task in backend.get_tasks_by_board(board_id)} == shown


@pytest.mark.parametrize(
    "active_board,expected_name,shown",
    [
        ("", "Vault", set(CARDS)),
        ("Work", "Work", {"acme-card"}),
    ],
)
def test_the_active_board_is_the_one_named_in_settings(
    board_vault: Path, active_board: str, expected_name: str, shown: set[str]
):
    backend = make_backend(board_vault, active_board)

    assert backend.active_board.name == expected_name
    assert titles(backend) == shown
    assert backend.get_warnings() == []


def test_an_unknown_active_board_shows_all_cards_with_a_warning(board_vault: Path):
    backend = make_backend(board_vault, "Hobbies")

    assert backend.active_board.name == "Vault"
    assert titles(backend) == set(CARDS)
    (warning,) = backend.get_warnings()
    assert "Hobbies" in warning


def test_board_infos_count_each_boards_own_cards(board_vault: Path):
    infos = make_backend(board_vault).get_board_infos()

    assert [(info["name"], info["amount_tasks"]) for info in infos] == [
        ("Vault", 4),
        ("Work", 1),
        ("Personal", 3),
        ("Everything", 4),
        ("Inbox", 2),
    ]


@pytest.mark.parametrize("active_board", ["", "Work", "Personal"])
def test_every_project_stays_writable_whatever_board_is_active(
    board_vault: Path, active_board: str
):
    projects = make_backend(board_vault, active_board).writable_projects()

    assert set(projects) == {"Acme", "Alpha", "Personal"}


@pytest.mark.parametrize(
    "active_board,offered",
    [
        ("", {"Acme", "Alpha", "Personal"}),
        ("Work", {"Acme"}),
        ("Personal", {"Alpha", "Personal"}),
    ],
)
def test_a_board_offers_only_its_own_projects_for_new_cards(
    board_vault: Path, active_board: str, offered: set[str]
):
    backend = make_backend(board_vault, active_board)
    backend.get_tasks_on_active_board()

    assert {c.name for c in backend.get_board_categories()} == offered
