"""Настройки проекта из файла состава: папка проекта, задача, последовательность ролей, проверка в браузере."""

from dataclasses import dataclass


@dataclass(frozen = True)
class ProjectSettings:
    """
    Настройки проекта.

        path: папка проекта.
        task: задача пользователя.
        roles: последовательность ролей пайплайна.
        browser_check: проверка приложения в браузере: веб-тестировщик и инструмент check_in_browser.
    """

    path: str
    task: str
    roles: tuple[str, ...]
    browser_check: bool
