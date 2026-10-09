"""Защита для команд оболочки на macOS: запуск под sandbox-exec, запись только в разрешённые
папки, чтение закрытых файлов и папок запрещено, сигналы - только процессам своей песочницы.

Сеть и запуск процессов не ограничиваются. На других системах команда запускается без защиты,
в журнал пишется предупреждение.
"""

import functools
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Программа песочницы macOS.
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")

# Папки, куда запись разрешена всегда: временные папки системы и кэши uv, npm, pip.
ALWAYS_WRITABLE = (
    Path("/private/tmp"),
    Path("/private/var/folders"),
    Path.home() / ".cache" / "uv",
    Path.home() / ".npm",
    Path.home() / ".cache" / "pip",
)

# Знаки, которые в регулярном выражении профиля значат не сами себя.
REGEX_SPECIAL_CHARACTERS = "\\.^$*+?()[]{}|"


@dataclass(frozen = True)
class ReadRestrictions:
    """
    Запреты чтения для команды.

        root: папка, внутри которой действуют запреты имён файлов.
        closed_file_names: имена файлов, закрытых на любой глубине внутри root.
        closed_dirs: папки, закрытые целиком.
        open_dirs: папки внутри закрытых, открытые для чтения.
    """

    root: Path
    closed_file_names: tuple[str, ...]
    closed_dirs: tuple[Path, ...]
    open_dirs: tuple[Path, ...]


# Устройства, без записи в которые ломаются обычные команды.
WRITABLE_DEVICES = ('(literal "/dev/null")', '(literal "/dev/tty")', '(regex #"^/dev/fd/")')


def sandbox_argv(
    *,
    argv: list[str],
    write_roots: tuple[Path, ...],
    read_restrictions: ReadRestrictions,
) -> list[str]:
    """
    Оборачивает команду в sandbox-exec: запись только в указанные папки и ALWAYS_WRITABLE,
    чтение закрытых файлов и папок запрещено, сигналы - только процессам этой песочницы.

        argv: команда с аргументами.
        write_roots: папки, куда команде разрешена запись.
        read_restrictions: запреты чтения.

    Возвращает: Команду под песочницей; на других системах — исходную команду.
    """
    if sys.platform != "darwin" or not SANDBOX_EXEC.exists():
        _warn_unprotected()
        return argv

    profile = _profile(write_roots = write_roots, read_restrictions = read_restrictions)

    return [str(SANDBOX_EXEC), "-p", profile, *argv]


def _profile(*, write_roots: tuple[Path, ...], read_restrictions: ReadRestrictions) -> str:
    """
    Собирает профиль песочницы: всё разрешено, кроме записи вне разрешённых папок, чтения
    закрытых файлов и папок и сигналов процессам вне этой песочницы.

    Из подходящих правил песочница применяет последнее, поэтому открытые папки идут после
    закрытых.

        write_roots: папки, куда команде разрешена запись.
        read_restrictions: запреты чтения.

    Возвращает: Текст профиля sandbox-exec.
    """
    folders = [_subpath(path = root) for root in (*ALWAYS_WRITABLE, *write_roots)]
    root_pattern = _regex_escape(text = str(read_restrictions.root.resolve()))
    closed_files = [
        f'(regex #"^{root_pattern}/(.*/)?{_regex_escape(text = name)}$")'
        for name in read_restrictions.closed_file_names
    ]
    closed_dirs = [_subpath(path = folder) for folder in read_restrictions.closed_dirs]
    open_dirs = [_subpath(path = folder) for folder in read_restrictions.open_dirs]

    rules = [
        "(version 1)(allow default)(deny file-write*)",
        f"(allow file-write* {' '.join((*WRITABLE_DEVICES, *folders))})",
        "(deny signal)(allow signal (target same-sandbox))",
    ]
    if closed_files or closed_dirs:
        rules.append(f"(deny file-read-data {' '.join((*closed_files, *closed_dirs))})")
    if open_dirs:
        rules.append(f"(allow file-read-data {' '.join(open_dirs)})")

    return "".join(rules)


def _subpath(*, path: Path) -> str:
    """
    Собирает правило профиля для папки со всем содержимым.

        path: путь папки.

    Возвращает: Правило subpath с абсолютным путём.
    """
    return f'(subpath "{_quote(path = path.resolve())}")'


def _regex_escape(*, text: str) -> str:
    """
    Экранирует текст для регулярного выражения профиля.

        text: текст, который должен совпасть буквально.

    Возвращает: Текст с экранированными особыми знаками и кавычкой.
    """
    escaped = "".join(f"\\{character}" if character in REGEX_SPECIAL_CHARACTERS else character for character in text)

    return escaped.replace('"', '\\"')


def _quote(*, path: Path) -> str:
    """
    Экранирует путь для строки профиля.

        path: абсолютный путь.

    Возвращает: Путь с экранированными обратной косой чертой и кавычкой.
    """
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


@functools.cache
def _warn_unprotected() -> None:
    """
    Один раз на процесс пишет в журнал, что команды оболочки идут без защиты файлов.
    """
    logger.warning("sandbox-exec недоступен: команды оболочки агентов запускаются без защиты файлов")
