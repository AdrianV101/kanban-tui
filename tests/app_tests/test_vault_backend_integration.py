"""Integration tests for the vault backend in the TUI app."""

from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Label, Select

from kanban_tui.app import KanbanTui
from kanban_tui.config import Backends
from kanban_tui.modal.modal_confirm_screen import ModalConfirmScreen
from kanban_tui.modal.modal_task_screen import ModalTaskEditScreen
from kanban_tui.widgets.modal_task_widgets import CategorySelector
from kanban_tui.widgets.task_card import TaskCard
from tests.conftest import write_task_note

APP_SIZE = (150, 50)


async def test_warnings_are_shown_when_the_board_mounts(
    vault_app: KanbanTui, test_vault: Path
):
    (test_vault / "01-Projects/Alpha/tasks/broken.md").write_text(
        "---\ntype: task\nstatus: [unclosed\n---\n", encoding="utf-8"
    )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()

        messages = [n.message for n in vault_app._notifications]
        assert any("01-Projects/Alpha/tasks/broken.md" in m for m in messages)
        cards = list(vault_app.screen.query(TaskCard))
        assert {card.task_.title for card in cards} == {"one", "two"}


@pytest.mark.parametrize("problem", ["empty_path", "missing_path", "no_pyyaml"])
async def test_switching_to_an_unloadable_vault_is_refused(
    test_app: KanbanTui, test_vault: Path, monkeypatch, problem: str
):
    test_app.config.backend.vault_settings.vault_path = {
        "empty_path": "",
        "missing_path": (test_vault / "does-not-exist").as_posix(),
        "no_pyyaml": test_vault.as_posix(),
    }[problem]
    test_vault.mkdir(exist_ok=True)
    if problem == "no_pyyaml":

        def fail(name: str) -> str:
            raise PackageNotFoundError(name)

        monkeypatch.setattr("importlib.metadata.version", fail)

    async with test_app.run_test(size=APP_SIZE) as pilot:
        select = test_app.screen.query_one("#select_backend_mode", Select)
        select.value = f"   {Backends.VAULT}"
        await pilot.pause()

        assert test_app.config.backend.mode == Backends.SQLITE
        assert test_app.backend.__class__.__name__ == "SqliteBackend"
        assert any(n.severity == "warning" for n in test_app._notifications)


async def focus_card(app: KanbanTui, pilot, title: str) -> TaskCard:
    card = next(c for c in app.screen.query(TaskCard) if c.task_.title == title)
    card.focus()
    await pilot.pause()
    return card


def find_card(app: KanbanTui, title: str) -> TaskCard:
    return next(c for c in app.screen.query(TaskCard) if c.task_.title == title)


async def test_pressing_a_move_key_writes_the_note(
    vault_app: KanbanTui, test_vault: Path
):
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press("L")
        await pilot.pause()

        assert find_card(vault_app, "two").task_.column == 3
        text = (test_vault / "01-Projects/Alpha/tasks/two.md").read_text()
        assert "\nstatus: active\nboard: doing\n" in text


async def test_a_refused_move_is_shown(vault_app: KanbanTui, test_vault: Path):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")
        path.write_text(path.read_text().replace("board: ready", "board: proposed"))

        await pilot.press("L")
        await pilot.pause()

        assert any(n.title == "Status Update Failed" for n in vault_app._notifications)
        assert find_card(vault_app, "two").task_.column == 2


@pytest.mark.parametrize(
    "focused_title,expected_column",
    [("zero", 1), ("two", 2), ("one", 3), (None, 2)],
)
async def test_a_new_card_lands_in_the_focused_column(
    vault_app: KanbanTui,
    test_vault: Path,
    focused_title: str | None,
    expected_column: int,
):
    write_task_note(
        test_vault,
        "01-Projects/Alpha/tasks/zero.md",
        {"status": "pending", "board": "proposed"},
    )
    if focused_title is None:
        for note in (test_vault / "01-Projects/Alpha/tasks").glob("*.md"):
            note.unlink()
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        if focused_title:
            await focus_card(vault_app, pilot, focused_title)
        else:
            assert not list(vault_app.screen.query(TaskCard))

        await pilot.press("n")
        await pilot.press(*"Brand new")
        await pilot.click("#btn_continue")
        await pilot.pause()

        assert find_card(vault_app, "Brand new").task_.column == expected_column
        text = (test_vault / "00-Inbox/brand-new.md").read_text()
        assert "# Brand new" in text


async def test_the_new_card_form_offers_no_category_editing(vault_app: KanbanTui):
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()

        await pilot.press("n")
        await pilot.pause()

        selector = vault_app.screen.query_one(CategorySelector)
        values = [value for _, value in selector._options]
        assert CategorySelector.NEW not in values
        assert any(isinstance(value, int) for value in values)


async def test_a_refused_creation_keeps_the_typed_input(
    vault_app: KanbanTui, test_vault: Path
):
    (test_vault / "05-Templates/task.md").unlink()
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press("n")
        await pilot.press(*"Kept title")
        await pilot.click("#btn_continue")
        await pilot.pause()

        assert any(n.severity == "error" for n in vault_app._notifications)
        assert isinstance(vault_app.screen, ModalTaskEditScreen)
        assert vault_app.screen.query_one("#input_title", Input).value == "Kept title"
        assert not list(test_vault.rglob("kept-title*.md"))


async def test_archiving_from_the_board_keeps_the_note(
    vault_app: KanbanTui, test_vault: Path
):
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press("d")
        await pilot.pause()
        confirm = vault_app.screen
        assert isinstance(confirm, ModalConfirmScreen)
        assert "Archive task" in str(confirm.query_one("#btn_continue", Button).label)
        assert "The note is kept." in str(confirm.query_one(Label).render())
        await pilot.press("enter")
        await pilot.pause()

        assert not any(c.task_.title == "two" for c in vault_app.screen.query(TaskCard))
        text = (test_vault / "01-Projects/Alpha/tasks/two.md").read_text()
        assert "\nstatus: cancelled\n" in text


async def test_a_refused_archive_is_shown(vault_app: KanbanTui, test_vault: Path):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")
        path.write_text(path.read_text().replace("board: ready", "board: proposed"))
        changed = path.read_text()

        await pilot.press("d")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert any(n.severity == "error" for n in vault_app._notifications)
        assert find_card(vault_app, "two").task_.column == 2
        assert path.read_text() == changed


@pytest.mark.parametrize("trigger", ["e", "enter", "click"])
async def test_edit_opens_the_note_in_obsidian(
    vault_app: KanbanTui, monkeypatch, trigger: str
):
    opened: list[str] = []
    monkeypatch.setattr(
        "kanban_tui.widgets.task_card.open_note",
        lambda app, url: opened.append(url),
    )
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        card = await focus_card(vault_app, pilot, "two")

        if trigger == "click":
            await pilot.click(f"#{card.id}")
        else:
            await pilot.press(trigger)
        await pilot.pause()

        assert opened == [
            "obsidian://open?vault=vault&file=01-Projects%2FAlpha%2Ftasks%2Ftwo"
        ]
        assert not isinstance(vault_app.screen, ModalTaskEditScreen)


@pytest.mark.parametrize(("forward", "back"), [("down", "up"), ("j", "k")])
async def test_keys_move_the_selection_in_a_column_that_overflows(
    vault_app: KanbanTui, test_vault: Path, forward: str, back: str
):
    for index in range(30):
        write_task_note(
            test_vault,
            f"01-Projects/Alpha/tasks/extra-{index}.md",
            {"status": "pending", "board": "ready"},
        )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        first = find_card(vault_app, "two")
        cards = [c for c in first.parent.children if isinstance(c, TaskCard)]
        assert first.parent.max_scroll_y > 0

        cards[0].focus()
        await pilot.pause()
        await pilot.press(forward)
        await pilot.pause()
        assert vault_app.focused is cards[1]

        await pilot.press(back)
        await pilot.pause()
        assert vault_app.focused is cards[0]


@pytest.mark.parametrize("key", ["left", "right"])
async def test_side_arrows_change_column_when_a_column_overflows(
    vault_app: KanbanTui, test_vault: Path, key: str
):
    for index in range(30):
        write_task_note(
            test_vault,
            f"01-Projects/Alpha/tasks/extra-{index}.md",
            {"status": "pending", "board": "ready"},
        )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        start = find_card(vault_app, "two")
        start.focus()
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert vault_app.focused is not start


async def test_right_skips_empty_columns(vault_app: KanbanTui, test_vault: Path):
    write_task_note(
        test_vault, "01-Projects/Alpha/tasks/three.md", {"status": "active"}
    )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "one")
        await pilot.press("right")
        await pilot.pause()

        assert vault_app.focused.task_.title == "two"


async def test_left_skips_empty_columns_and_keeps_the_row_in_range(
    vault_app: KanbanTui, test_vault: Path
):
    write_task_note(
        test_vault,
        "01-Projects/Alpha/tasks/four.md",
        {"status": "pending", "board": "ready"},
    )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        ready = find_card(vault_app, "two").parent
        lower = [c for c in ready.children if isinstance(c, TaskCard)][1]
        lower.focus()
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()

        assert vault_app.focused.task_.title == "one"


@pytest.mark.parametrize("key", ["left", "right"])
async def test_side_keys_stay_put_when_every_other_column_is_empty(
    vault_app: KanbanTui, test_vault: Path, key: str
):
    write_task_note(
        test_vault,
        "01-Projects/Alpha/tasks/one.md",
        {"status": "pending", "board": "ready"},
    )

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        card = await focus_card(vault_app, pilot, "two")
        await pilot.press(key)
        await pilot.pause()

        assert vault_app.focused is card


def write_proposed_notes(test_vault: Path, count: int) -> None:
    for index in range(count):
        write_task_note(
            test_vault,
            f"01-Projects/Alpha/tasks/proposed-{index}.md",
            {"status": "pending"},
        )


def cards_in_column(app: KanbanTui, column: int) -> list[TaskCard]:
    return [c for c in app.screen.query(TaskCard) if c.task_.column == column]


async def test_archiving_a_proposed_card_needs_no_confirmation(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 1)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "proposed-0")

        await pilot.press("d")
        await pilot.pause()

        assert not isinstance(vault_app.screen, ModalConfirmScreen)
        text = (test_vault / "01-Projects/Alpha/tasks/proposed-0.md").read_text()
        assert "\nstatus: cancelled\n" in text


async def test_a_refused_proposed_archive_is_shown(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 1)
    path = test_vault / "01-Projects/Alpha/tasks/proposed-0.md"

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "proposed-0")
        path.write_text(path.read_text() + "\nboard: ready\n")
        path.write_text(path.read_text().replace("status: pending", "status: active"))
        changed = path.read_text()

        await pilot.press("d")
        await pilot.pause()

        assert any(n.severity == "error" for n in vault_app._notifications)
        assert path.read_text() == changed


@pytest.mark.parametrize(
    ("archived_row", "selected_row"),
    [(0, 0), (1, 1), (3, 2)],
    ids=["first", "middle", "last"],
)
async def test_archiving_keeps_the_selection_at_the_same_place_in_the_column(
    vault_app: KanbanTui, test_vault: Path, archived_row: int, selected_row: int
):
    write_proposed_notes(test_vault, 4)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        cards = cards_in_column(vault_app, 1)
        cards[archived_row].focus()
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()

        remaining = cards_in_column(vault_app, 1)
        assert len(remaining) == 3
        assert vault_app.focused is remaining[selected_row]


async def test_archiving_a_column_s_only_card_selects_the_nearest_column(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 1)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "proposed-0")

        await pilot.press("d")
        await pilot.pause()

        assert vault_app.focused.task_.title == "two"


@pytest.mark.parametrize(
    ("key", "column", "fields"),
    [
        ("1", 1, "\nstatus: pending\nboard: proposed\n"),
        ("3", 3, "\nstatus: active\nboard: doing\n"),
        ("4", 4, "\nstatus: active\nboard: in-review\n"),
        ("5", 5, "\nstatus: done\n"),
    ],
)
async def test_number_keys_move_the_card_to_that_column(
    vault_app: KanbanTui, test_vault: Path, key: str, column: int, fields: str
):
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press(key)
        await pilot.pause()

        assert find_card(vault_app, "two").task_.column == column
        text = (test_vault / "01-Projects/Alpha/tasks/two.md").read_text()
        assert fields in text


@pytest.mark.parametrize("key", ["2", "6", "9"], ids=["same", "hidden", "none"])
async def test_number_keys_without_a_new_column_leave_the_note_alone(
    vault_app: KanbanTui, test_vault: Path, key: str
):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    before = path.read_bytes()

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")

        await pilot.press(key)
        await pilot.pause()

        assert find_card(vault_app, "two").task_.column == 2
        assert path.read_bytes() == before


async def test_a_refused_number_key_move_is_shown(
    vault_app: KanbanTui, test_vault: Path
):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "two")
        path.write_text(path.read_text().replace("board: ready", "board: proposed"))

        await pilot.press("3")
        await pilot.pause()

        assert any(n.title == "Status Update Failed" for n in vault_app._notifications)
        assert find_card(vault_app, "two").task_.column == 2


@pytest.mark.parametrize(
    ("moved_row", "selected_row"),
    [(0, 0), (1, 1), (3, 2)],
    ids=["first", "middle", "last"],
)
async def test_number_keys_leave_the_selection_in_the_column(
    vault_app: KanbanTui, test_vault: Path, moved_row: int, selected_row: int
):
    write_proposed_notes(test_vault, 4)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        cards = cards_in_column(vault_app, 1)
        moved_id = cards[moved_row].task_.task_id
        cards[moved_row].focus()
        await pilot.pause()

        await pilot.press("2")
        await pilot.pause()

        remaining = cards_in_column(vault_app, 1)
        assert len(remaining) == 3
        assert all(c.task_.task_id != moved_id for c in remaining)
        assert vault_app.focused is remaining[selected_row]


async def test_number_keys_can_work_down_a_column(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 3)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        cards_in_column(vault_app, 1)[0].focus()
        await pilot.pause()

        await pilot.press("2", "3", "5")
        await pilot.pause()

        assert cards_in_column(vault_app, 1) == []
        for name, fields in [
            ("proposed-0", "\nstatus: pending\nboard: ready\n"),
            ("proposed-1", "\nstatus: active\nboard: doing\n"),
            ("proposed-2", "\nstatus: done\n"),
        ]:
            note = test_vault / f"01-Projects/Alpha/tasks/{name}.md"
            assert fields in note.read_text()


async def test_number_key_on_a_column_s_only_card_selects_the_nearest_column(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 1)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await focus_card(vault_app, pilot, "proposed-0")

        await pilot.press("5")
        await pilot.pause()

        assert vault_app.focused.task_.title == "two"


async def test_a_refused_number_key_move_keeps_the_selection(
    vault_app: KanbanTui, test_vault: Path
):
    path = test_vault / "01-Projects/Alpha/tasks/two.md"
    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        card = await focus_card(vault_app, pilot, "two")
        path.write_text(path.read_text().replace("board: ready", "board: proposed"))

        await pilot.press("3")
        await pilot.pause()

        assert vault_app.focused is card


async def test_side_move_keys_still_follow_the_card(
    vault_app: KanbanTui, test_vault: Path
):
    write_proposed_notes(test_vault, 2)

    async with vault_app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        card = cards_in_column(vault_app, 1)[0]
        task_id = card.task_.task_id
        card.focus()
        await pilot.pause()

        await pilot.press("L")
        await pilot.pause()

        assert vault_app.focused.task_.task_id == task_id
        assert vault_app.focused.task_.column == 2
