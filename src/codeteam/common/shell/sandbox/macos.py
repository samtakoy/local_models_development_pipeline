"""Песочница macOS: запуск под sandbox-exec, запись только в разрешённые папки, сигналы только внутри
песочницы. Чтение, сеть и запуск процессов не ограничиваются."""

from pathlib import Path

# Программа песочницы macOS.
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")

# Временные папки macOS, куда запись разрешена всегда.
MACOS_TEMP_DIRS = (Path("/private/tmp"), Path("/private/var/folders"))

# Устройства, без записи в которые ломаются обычные команды.
WRITABLE_DEVICES = ('(literal "/dev/null")', '(literal "/dev/tty")', '(regex #"^/dev/fd/")')


def macos_sandbox_argv(*, argv: list[str], write_roots: tuple[Path, ...]) -> list[str]:
    """
    Оборачивает запуск программы в sandbox-exec.

        argv: программа с аргументами.
        write_roots: папки, куда разрешена запись, кроме временных папок macOS.

    Возвращает: Запуск программы под песочницей.
    """
    return [str(SANDBOX_EXEC), "-p", _profile(write_roots = (*MACOS_TEMP_DIRS, *write_roots)), *argv]


def _profile(*, write_roots: tuple[Path, ...]) -> str:
    """
    Собирает профиль песочницы: всё разрешено, кроме записи вне write_roots и сигналов процессам вне
    этой песочницы.

        write_roots: папки, куда разрешена запись.

    Возвращает: Текст профиля sandbox-exec.
    """
    folders = [_subpath(path = root) for root in write_roots]

    return (
        "(version 1)(allow default)(deny file-write*)"
        f"(allow file-write* {' '.join((*WRITABLE_DEVICES, *folders))})"
        "(deny signal)(allow signal (target same-sandbox))"
    )


def _subpath(*, path: Path) -> str:
    """
    Собирает правило профиля для папки со всем содержимым.

        path: путь папки.

    Возвращает: Правило subpath с абсолютным путём.
    """
    return f'(subpath "{_quote(path = path.resolve())}")'


def _quote(*, path: Path) -> str:
    """
    Экранирует путь для строки профиля.

        path: абсолютный путь.

    Возвращает: Путь с экранированными обратной косой чертой и кавычкой.
    """
    return str(path).replace("\\", "\\\\").replace('"', '\\"')
