"""Настройки проекта из файла состава: папка проекта, задача, последовательность ролей."""

from dataclasses import dataclass


@dataclass(frozen = True)
class ProjectSettings:
    """
    Настройки проекта.

        path: папка проекта.
        task: задача пользователя.
        roles: последовательность ролей пайплайна.
    """

    path: str
    task: str
    roles: tuple[str, ...]
