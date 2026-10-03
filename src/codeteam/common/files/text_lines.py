"""Строки текстового файла: деление, нумерация с пределами объёма, список папки."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen = True)
class NumberedPage:
    """
    Часть файла с номерами строк.

        lines: строки вида "номер:текст".
        first_number: номер первой показанной строки, от 1.
        last_number: номер последней показанной строки.
        total: число строк в файле.
    """

    lines: list[str]
    first_number: int
    last_number: int
    total: int


def split_lines(*, text: str) -> list[str]:
    """
    Делит текст на строки по переводу строки, без завершающих \\r.

        text: содержимое файла.

    Возвращает: Строки файла; перевод строки в конце файла пустой строки не даёт.
    """
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()

    return [line.removesuffix("\r") for line in lines]


def number_lines(
    *,
    lines: list[str],
    offset: int,
    limit: int,
    line_width: int,
    character_limit: int,
) -> NumberedPage:
    """
    Нумерует часть строк с обрезкой длинных строк и общего объёма.

    Первая строка части показывается всегда, даже если она длиннее character_limit.

        lines: все строки файла.
        offset: номер первой строки, от 1, не больше числа строк.
        limit: наибольшее число строк.
        line_width: длина строки, дальше строка обрезается.
        character_limit: наибольший объём части в символах.

    Возвращает: Часть файла с номерами строк.
    """
    shown: list[str] = []
    characters = 0
    last_number = offset - 1
    for number in range(offset, min(offset + limit, len(lines) + 1)):
        line = lines[number - 1]
        is_cut = len(line) > line_width
        if is_cut:
            line = line[:line_width] + "… (строка обрезана)"

        numbered = f"{number}:{line}"
        if characters + len(numbered) > character_limit and shown:
            break

        shown.append(numbered)
        characters += len(numbered) + 1
        last_number = number

    return NumberedPage(
        lines = shown,
        first_number = offset,
        last_number = last_number,
        total = len(lines),
    )


def list_directory(*, path: Path) -> list[str]:
    """
    Перечисляет содержимое папки по алфавиту, папки с косой чертой в конце.

        path: путь папки.

    Возвращает: Имена элементов папки.
    """
    return sorted(
        f"{entry.name}/" if entry.is_dir() else entry.name
        for entry in path.iterdir()
    )
