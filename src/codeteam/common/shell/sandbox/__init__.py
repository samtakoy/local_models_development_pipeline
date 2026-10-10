"""Песочница команд агента: запись только в разрешённые папки, сигналы только внутри песочницы.

macOS — sandbox-exec, Linux — Landlock. На других системах и без Landlock нужной версии программа
запускается без песочницы, в журнал пишется предупреждение. В Linux песочницу можно вложить в песочницу:
из вложенной нельзя посылать сигналы процессам внешней; на macOS песочницы не вкладываются.
"""

import functools
import logging
import sys
from pathlib import Path

from codeteam.common.shell.sandbox import landlock_exec
from codeteam.common.shell.sandbox.macos import SANDBOX_EXEC, macos_sandbox_argv

logger = logging.getLogger(__name__)

# Папки кэшей в домашней папке, куда запись разрешена всегда: общая папка кэшей программ и кэш npm.
HOME_CACHE_DIRS = (
    Path.home() / ".cache",
    Path.home() / ".npm",
)

# Временные папки Linux, куда запись разрешена всегда.
LINUX_TEMP_DIRS = (Path("/tmp"), Path("/var/tmp"), Path("/dev/shm"))

# Устройства Linux, без записи в которые ломаются обычные команды.
LINUX_WRITABLE_DEVICES = (Path("/dev/null"), Path("/dev/tty"))


def sandboxed_argv(*, argv: list[str], write_roots: tuple[Path, ...]) -> list[str]:
    """
    Оборачивает запуск программы в песочницу системы: запись только в write_roots, кэши программ и
    временные папки, сигналы только внутри песочницы.

        argv: программа с аргументами.
        write_roots: папки, куда разрешена запись.

    Возвращает: Запуск программы под песочницей; без песочницы — исходный argv.
    """
    if not is_sandbox_available():
        _warn_unprotected()
        return argv

    roots = (*write_roots, *HOME_CACHE_DIRS)
    if sys.platform == "darwin":
        return macos_sandbox_argv(argv = argv, write_roots = roots)

    return _landlock_argv(argv = argv, write_roots = roots)


def nested_sandbox_argv(*, argv: list[str], write_roots: tuple[Path, ...]) -> list[str]:
    """
    Оборачивает запуск программы из процесса песочницы sandboxed_argv во вложенную песочницу с теми же
    правами: процессы вложенной песочницы не могут посылать сигналы процессам внешней.

        argv: программа с аргументами.
        write_roots: папки, куда разрешена запись.

    Возвращает: В Linux — запуск программы во вложенной песочнице; на macOS и без песочницы — исходный argv:
        программа работает в песочнице запускающего процесса.
    """
    if sys.platform != "linux" or not is_sandbox_available():
        return argv

    return _landlock_argv(argv = argv, write_roots = (*write_roots, *HOME_CACHE_DIRS))


def is_sandbox_available() -> bool:
    """
    Проверяет, есть ли на этой машине песочница: sandbox-exec на macOS или Landlock нужной версии в Linux.

    Возвращает: True, если песочница доступна.
    """
    if sys.platform == "darwin":
        return SANDBOX_EXEC.exists()

    if sys.platform == "linux":
        return landlock_exec.landlock_abi_version() >= landlock_exec.MINIMAL_ABI_VERSION

    return False


def _landlock_argv(*, argv: list[str], write_roots: tuple[Path, ...]) -> list[str]:
    """
    Оборачивает запуск программы в песочницу Landlock.

        argv: программа с аргументами.
        write_roots: папки, куда разрешена запись, кроме временных папок и устройств Linux.

    Возвращает: Запуск программы через landlock_exec.
    """
    write_options = []
    for root in (*write_roots, *LINUX_TEMP_DIRS, *LINUX_WRITABLE_DEVICES):
        write_options += [landlock_exec.WRITE_OPTION, str(root.resolve())]

    return [sys.executable, "-I", landlock_exec.__file__, *write_options, landlock_exec.PROGRAM_SEPARATOR, *argv]


@functools.cache
def _warn_unprotected() -> None:
    """
    Один раз на процесс пишет в журнал, что команды агентов идут без песочницы.
    """
    logger.warning(
        "песочница недоступна (нужен macOS или Linux с Landlock версии %s): команды агентов запускаются "
        "без защиты файлов и процессов",
        landlock_exec.MINIMAL_ABI_VERSION,
    )
