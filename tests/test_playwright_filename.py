"""Тесты проверки filename инструментов браузера: файлы пропускаются только в папку CHECK_DIR проекта."""

from pathlib import Path

import pytest

from codeteam.core.roles.web_tester.config import check_playwright_filename


@pytest.mark.parametrize("filename", ["tmp_check/home_page.png", "tmp_check/screenshots/home_page.png"])
def test_filename_inside_check_dir_is_allowed(tmp_path: Path, filename: str) -> None:
    """
    Файл внутри CHECK_DIR проекта пропускается.
    """
    refusal = check_playwright_filename(
        "browser_take_screenshot",
        {"filename": filename},
        project_dir = tmp_path,
    )

    assert refusal is None


def test_call_without_filename_is_allowed(tmp_path: Path) -> None:
    """
    Вызов без filename пропускается.
    """
    refusal = check_playwright_filename("browser_console_messages", {"level": "error"}, project_dir = tmp_path)

    assert refusal is None


@pytest.mark.parametrize(
    "filename",
    ["screenshots/home_page.png", "src/app.py", "tmp_check/../src/app.py", "/tmp/home_page.png"],
)
def test_filename_outside_check_dir_is_refused(tmp_path: Path, filename: str) -> None:
    """
    Файл вне CHECK_DIR проекта — в корне, поверх файла проекта, через .. или по абсолютному пути — получает
    отказ, в котором назван этот filename.
    """
    refusal = check_playwright_filename(
        "browser_take_screenshot",
        {"filename": filename},
        project_dir = tmp_path,
    )

    assert refusal is not None
    assert filename in refusal
