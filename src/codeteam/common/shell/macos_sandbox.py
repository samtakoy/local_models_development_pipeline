"""Защита записи для команд оболочки на macOS: запуск под sandbox-exec, запись только в разрешённые папки.

Чтение, сеть и запуск процессов не ограничиваются. На других системах команда запускается без
защиты, в журнал пишется предупреждение.
"""

import functools
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Программа песочницы macOS.
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")

# Папки, куда запись разрешена всегда: временные папки системы и кэш uv.
ALWAYS_WRITABLE = (
    Path("/private/tmp"),
    Path("/private/var/folders"),
    Path.home() / ".cache" / "uv",
)

# Устройства, без записи в которые ломаются обычные команды.
WRITABLE_DEVICES = ('(literal "/dev/null")', '(literal "/dev/tty")', '(regex #"^/dev/fd/")')


def sandbox_argv(*, argv: list[str], write_roots: tuple[Path, ...]) -> list[str]:
    """
    Оборачивает команду в sandbox-exec, разрешая запись только в указанные папки и ALWAYS_WRITABLE.

        argv: команда с аргументами.
        write_roots: папки, куда команде разрешена запись.

    Возвращает: Команду под песочницей; на других системах — исходную команду.
    """
    if sys.platform != "darwin" or not SANDBOX_EXEC.exists():
        _warn_unprotected()
        return argv

    return [str(SANDBOX_EXEC), "-p", _profile(write_roots = write_roots), *argv]


def _profile(*, write_roots: tuple[Path, ...]) -> str:
    """
    Собирает профиль песочницы: всё разрешено, кроме записи вне разрешённых папок.

        write_roots: папки, куда команде разрешена запись.

    Возвращает: Текст профиля sandbox-exec.
    """
    folders = [f'(subpath "{_quote(path = root.resolve())}")' for root in (*ALWAYS_WRITABLE, *write_roots)]

    return (
        "(version 1)(allow default)(deny file-write*)"
        f"(allow file-write* {' '.join((*WRITABLE_DEVICES, *folders))})"
    )


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
    Один раз на процесс пишет в журнал, что команды оболочки идут без защиты записи.
    """
    logger.warning("sandbox-exec недоступен: команды оболочки агентов запускаются без защиты записи")
