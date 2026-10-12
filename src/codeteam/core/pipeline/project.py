"""Настройки проекта из файла состава: папка проекта, задача, последовательность ролей, проверка в браузере,
советник по документации."""

from dataclasses import dataclass


@dataclass(frozen = True)
class ProjectSettings:
    """
    Настройки проекта.

        path: папка проекта.
        task: задача пользователя.
        roles: последовательность ролей пайплайна.
        browser_check: проверка приложения в браузере: веб-тестировщик и инструмент check_in_browser.
        library_docs: советник по документации библиотек: инструмент query_library_docs и прогрев Context7 MCP.
    """

    path: str
    task: str
    roles: tuple[str, ...]
    browser_check: bool
    library_docs: bool
