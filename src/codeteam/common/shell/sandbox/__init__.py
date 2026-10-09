"""Песочница команд агента: запись только в разрешённые папки, сигналы только внутри песочницы.

macOS — sandbox-exec, Linux — Landlock. На других системах и без Landlock нужной версии программа
запускается без песочницы, в журнал пишется предупреждение.
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
    roots = (*write_roots, *HOME_CACHE_DIRS)
    if sys.platform == "darwin" and SANDBOX_EXEC.exists():
        return macos_sandbox_argv(argv = argv, write_roots = roots)

    if sys.platform == "linux" and landlock_exec.landlock_abi_version() >= landlock_exec.MINIMAL_ABI_VERSION:
        write_options = []
        for root in (*roots, *LINUX_TEMP_DIRS, *LINUX_WRITABLE_DEVICES):
            write_options += [landlock_exec.WRITE_OPTION, str(root.resolve())]

        return [sys.executable, "-I", landlock_exec.__file__, *write_options, landlock_exec.PROGRAM_SEPARATOR, *argv]

    _warn_unprotected()

    return argv


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
