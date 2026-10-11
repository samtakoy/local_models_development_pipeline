"""Отказы файловых инструментов по пути: инструменты запоминают их за шаг агента, хуки шага получают их
после шага."""

from dataclasses import dataclass


@dataclass(frozen = True)
class PathRefusal:
    """
    Отказ файлового инструмента по пути: путь вне папок, доступных вызову.

        path: путь от агента.
        is_write: отказ записи; иначе отказ чтения.
    """

    path: str
    is_write: bool


class PathRefusals:
    """
    Отказы файловых инструментов по пути за текущий шаг агента; общие для всех файловых инструментов агента.
    """

    def __init__(self) -> None:
        self._refusals: list[PathRefusal] = []

    def add(self, *, refusal: PathRefusal) -> None:
        """
        Запоминает отказ.

            refusal: отказ по пути.
        """
        self._refusals.append(refusal)

    def take(self) -> tuple[PathRefusal, ...]:
        """
        Забирает отказы шага и очищает сборщик.

        Возвращает: Отказы по порядку.
        """
        refusals = tuple(self._refusals)
        self._refusals.clear()

        return refusals
