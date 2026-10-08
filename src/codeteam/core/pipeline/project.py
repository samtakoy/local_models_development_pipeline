"""Настройки проекта из файла состава: папка проекта, задача, режимы ревью."""

from dataclasses import dataclass
from enum import StrEnum


class ReviewMode(StrEnum):
    """
    Режим ревью роли.

        OFF: ревьюера нет.
        ON: ревью есть; после последнего круга с вердиктом «доработать» пайплайн идёт дальше.
        STRICT: ревью есть; после последнего круга с вердиктом «доработать» прогон останавливается.
    """

    OFF = "off"
    ON = "on"
    STRICT = "strict"


@dataclass(frozen = True)
class ReviewSettings:
    """
    Режимы ревью ролей: поле на каждую роль, у которой есть ревьюер.

        architect: режим ревью архитектора.
        developer: режим приёмки этапа после разработчика.
    """

    architect: ReviewMode
    developer: ReviewMode


@dataclass(frozen = True)
class ProjectSettings:
    """
    Настройки проекта.

        path: папка проекта.
        task: задача пользователя.
        review: режимы ревью ролей.
    """

    path: str
    task: str
    review: ReviewSettings
