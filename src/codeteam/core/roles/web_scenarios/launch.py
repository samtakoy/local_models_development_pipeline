"""Ответ составителя сценариев: файл запуска приложения и файлы сценариев в черновике."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from codeteam.core.agent.workspace import DRAFT_SECTION_PATTERN
from codeteam.core.roles.browser_checker.tool import LOCAL_HOSTS
from codeteam.core.roles.web_scenarios.prompts import BAD_LAUNCH_LINE_REMARK, MISSING_LAUNCH_FIELD_REMARK, \
    MISSING_LAUNCH_FILE_REMARK, NOT_LOCAL_LAUNCH_URL_REMARK

# Файл запуска приложения в черновике составителя сценариев.
LAUNCH_FILE_NAME = "000_launch.md"

# Поля файла запуска: команда запуска приложения и его адрес.
COMMAND_FIELD = "command"
URL_FIELD = "url"


@dataclass(frozen = True)
class AppLaunch:
    """
    Запуск приложения для проверки в браузере.

        command: команда запуска приложения из папки проекта.
        url: адрес приложения на этом компьютере.
    """

    command: str
    url: str


class LaunchFileError(ValueError):
    """Файл запуска не читается: текст ошибки — замечание составителю сценариев."""


def read_app_launch(*, draft_dir: Path) -> AppLaunch:
    """
    Читает файл запуска: строки «command: …» и «url: …», адрес на 127.0.0.1 или localhost.
    Ошибку поднимает LaunchFileError.

        draft_dir: папка черновика составителя сценариев.

    Возвращает: Запуск приложения.
    """
    launch_path = draft_dir / LAUNCH_FILE_NAME
    if not launch_path.is_file():
        raise LaunchFileError(MISSING_LAUNCH_FILE_REMARK.format(launch_file = LAUNCH_FILE_NAME))

    fields = {}
    for line in launch_path.read_text(encoding = "utf-8", errors = "replace").splitlines():
        if not line.strip():
            continue

        name, separator, value = line.partition(":")
        if not separator or name.strip() not in (COMMAND_FIELD, URL_FIELD) or not value.strip():
            raise LaunchFileError(BAD_LAUNCH_LINE_REMARK.format(launch_file = LAUNCH_FILE_NAME, line = line.strip()))

        fields[name.strip()] = value.strip()

    missing = [name for name in (COMMAND_FIELD, URL_FIELD) if name not in fields]
    if missing:
        raise LaunchFileError(
            MISSING_LAUNCH_FIELD_REMARK.format(launch_file = LAUNCH_FILE_NAME, fields = ", ".join(missing))
        )

    parsed = urlparse(fields[URL_FIELD])
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
        raise LaunchFileError(
            NOT_LOCAL_LAUNCH_URL_REMARK.format(launch_file = LAUNCH_FILE_NAME, url = fields[URL_FIELD])
        )

    return AppLaunch(command = fields[COMMAND_FIELD], url = fields[URL_FIELD])


def scenario_files(*, draft_dir: Path) -> list[Path]:
    """
    Находит файлы сценариев: разделы черновика <номер>_<тема>.md, кроме файла запуска.

        draft_dir: папка черновика составителя сценариев.

    Возвращает: Файлы сценариев по порядку имён.
    """
    return [
        path
        for path in sorted(draft_dir.glob("*.md"))
        if path.name != LAUNCH_FILE_NAME and DRAFT_SECTION_PATTERN.match(path.name)
    ]
