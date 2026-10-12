"""Уровень размышления модели: значения и перевод в параметр think сервера ollama."""

from enum import StrEnum


class ReasoningLevel(StrEnum):
    """
    Уровень размышления модели.

        NONE: размышление выключено.
        DEFAULT: уровень сервера моделей.
        LOW: короткое размышление.
        MEDIUM: среднее размышление.
        HIGH: длинное размышление.
    """

    NONE = "none"
    DEFAULT = "default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def ollama_think(*, level: ReasoningLevel | None) -> bool | str:
    """
    Переводит уровень в значение think интерфейса ollama.

        level: уровень размышления, None - размышление выключено.

    Возвращает:
        False при выключенном размышлении (None или NONE), True при уровне сервера, имя уровня
        в остальных случаях.
    """
    if level is None or level is ReasoningLevel.NONE:
        return False

    if level is ReasoningLevel.DEFAULT:
        return True

    return level.value
