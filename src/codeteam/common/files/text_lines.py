"""Строки текстового файла: отличие текста от двоичного файла, деление, нумерация с пределами
объёма, список папки и сведения о файлах."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Предел размера файла для подсчёта строк в file_stats, байты: файл больше не читается.
FILE_STATS_READ_LIMIT_BYTES = 1024 * 1024


class FileKind(Enum):
    """
    Вид файла для сведений о папке.

    Значения:
        TEXT: текстовый файл (decode_text).
        BINARY: двоичный файл (decode_text).
        LARGE: файл больше FILE_STATS_READ_LIMIT_BYTES, не читался.
    """

    TEXT = "text"
    BINARY = "binary"
    LARGE = "large"


@dataclass(frozen = True)
class FileStats:
    """
    Сведения о файле.

        kind: вид файла.
        size_bytes: размер в байтах.
        line_count: число строк для текстового файла; None для остальных.
    """

    kind: FileKind
    size_bytes: int
    line_count: int | None


@dataclass(frozen = True)
class DirectoryEntry:
    """
    Элемент папки.

        name: имя без пути.
        is_dir: True для папки.
        path: полный путь элемента.
    """

    name: str
    is_dir: bool
    path: Path


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


def decode_text(*, content: bytes) -> str | None:
    """
    Переводит содержимое файла в текст. Файл двоичный, если в нём есть нулевой байт или он
    не в кодировке utf-8.

        content: содержимое файла.

    Возвращает: Текст файла; None для двоичного файла.
    """
    if b"\0" in content:
        return None

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


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


def list_directory(*, path: Path) -> list[DirectoryEntry]:
    """
    Перечисляет содержимое папки по алфавиту имён. Файлы не читает.

        path: путь папки.

    Возвращает: Элементы папки.
    """
    entries = [
        DirectoryEntry(name = entry.name, is_dir = entry.is_dir(), path = entry)
        for entry in path.iterdir()
    ]

    return sorted(entries, key = lambda entry: entry.name)


def file_stats(*, path: Path) -> FileStats | None:
    """
    Собирает сведения о файле: вид, размер и число строк текстового файла.

    Файл больше FILE_STATS_READ_LIMIT_BYTES не читается.

        path: путь файла.

    Возвращает: Сведения о файле; None, если это не обычный файл или его не удалось прочитать.
    """
    if not path.is_file():
        return None

    try:
        size_bytes = path.stat().st_size
        if size_bytes > FILE_STATS_READ_LIMIT_BYTES:
            return FileStats(kind = FileKind.LARGE, size_bytes = size_bytes, line_count = None)

        text = decode_text(content = path.read_bytes())
    except OSError:
        return None

    if text is None:
        return FileStats(kind = FileKind.BINARY, size_bytes = size_bytes, line_count = None)

    return FileStats(kind = FileKind.TEXT, size_bytes = size_bytes, line_count = len(split_lines(text = text)))
