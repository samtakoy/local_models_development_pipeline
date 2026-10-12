"""Тесты ответа составителя сценариев: разбор файла запуска, список сценариев, проверка сдачи."""

from pathlib import Path

import pytest

from codeteam.core.agent.answer_checks import AnswerContext
from codeteam.core.roles.web_scenarios import AppLaunch, LaunchFileError, read_app_launch, scenario_files
from codeteam.core.roles.web_scenarios.checks import scenarios_check
from codeteam.core.roles.web_scenarios.launch import LAUNCH_FILE_NAME


def _draft(*, tmp_path: Path, launch: str | None, scenario_names: tuple[str, ...]) -> Path:
    """
    Пишет черновик составителя сценариев.

        tmp_path: папка теста.
        launch: текст файла запуска; None — файла нет.
        scenario_names: имена файлов сценариев.

    Возвращает: Папку черновика.
    """
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    if launch is not None:
        (draft_dir / LAUNCH_FILE_NAME).write_text(launch, encoding = "utf-8")
    for name in scenario_names:
        (draft_dir / name).write_text("# Сценарий\n1. Открой адрес приложения.\n", encoding = "utf-8")

    return draft_dir


def test_launch_file_is_read(tmp_path: Path) -> None:
    """Две строки command и url, пустые строки и пробелы вокруг значений не мешают."""
    draft_dir = _draft(
        tmp_path = tmp_path,
        launch = "\ncommand:  uv run python src/main.py \nurl: http://127.0.0.1:8050/\n",
        scenario_names = (),
    )

    assert read_app_launch(draft_dir = draft_dir) == AppLaunch(
        command = "uv run python src/main.py",
        url = "http://127.0.0.1:8050/",
    )


@pytest.mark.parametrize(
    "launch",
    [
        None,
        "command: uv run app\n",
        "command: uv run app\nurl: http://example.com/\n",
        "command: uv run app\nurl: http://127.0.0.1:8050/\nport: 8050\n",
        "# Запуск\ncommand: uv run app\nurl: http://127.0.0.1:8050/\n",
        "command:\nurl: http://127.0.0.1:8050/\n",
    ],
)
def test_bad_launch_file_is_rejected(tmp_path: Path, launch: str | None) -> None:
    """Нет файла, нет строки, адрес не локальный, лишняя строка или пустая команда — ошибка с замечанием."""
    draft_dir = _draft(tmp_path = tmp_path, launch = launch, scenario_names = ())

    with pytest.raises(LaunchFileError):
        read_app_launch(draft_dir = draft_dir)


def test_scenario_files_are_sections_without_launch_file(tmp_path: Path) -> None:
    """Сценарии — разделы черновика по порядку имён, без файла запуска и файлов не по имени раздела."""
    draft_dir = _draft(
        tmp_path = tmp_path,
        launch = "command: uv run app\nurl: http://localhost:8050/\n",
        scenario_names = ("200_open_deck.md", "100_add_source.md", "notes.md"),
    )

    assert [path.name for path in scenario_files(draft_dir = draft_dir)] == ["100_add_source.md", "200_open_deck.md"]


@pytest.mark.parametrize(
    ("launch", "scenario_names", "has_remark"),
    [
        ("command: uv run app\nurl: http://127.0.0.1:8050/\n", ("100_a.md",), False),
        ("command: uv run app\nurl: http://127.0.0.1:8050/\n", (), True),
        (None, ("100_a.md",), True),
    ],
)
def test_scenarios_check(tmp_path: Path, launch: str | None, scenario_names: tuple[str, ...], has_remark: bool) -> None:
    """Сдача: замечание, если файл запуска не читается или нет ни одного сценария."""
    draft_dir = _draft(tmp_path = tmp_path, launch = launch, scenario_names = scenario_names)

    remark = scenarios_check(AnswerContext(project_dir = tmp_path, draft_dir = draft_dir))

    assert (remark is not None) == has_remark
