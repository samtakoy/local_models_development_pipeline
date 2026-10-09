"""Запуск программы под Landlock (Linux): запись только в указанные папки, сигналы только внутри песочницы.

Запуск: python landlock_exec.py --write <путь> [--write <путь> ...] -- <программа> [аргументы]

Ставит ограничения на себя и заменяет себя программой: ограничения переходят к ней и ко всем её
потомкам. Чтение не ограничивается. Использует только стандартную библиотеку: codeteam запускает
его отдельной программой и берёт из него проверку версии Landlock.
"""

import ctypes
import os
import sys

# Номера системных вызовов Landlock: одинаковые на x86_64 и arm64.
_CREATE_RULESET_SYSCALL = 444
_ADD_RULE_SYSCALL = 445
_RESTRICT_SELF_SYSCALL = 446

# Флаг landlock_create_ruleset: вернуть версию Landlock вместо создания набора правил.
_CREATE_RULESET_VERSION = 1

# Вид правила: доступ к файлам внутри папки.
_RULE_PATH_BENEATH = 1

# prctl: запрет повышать права, без него Landlock не ставится.
_PR_SET_NO_NEW_PRIVS = 38

# Ограничение сигналов: только процессам своей песочницы.
_SCOPE_SIGNAL = 1 << 1

# Права записи в файл: открыть на запись, обрезать.
_FILE_WRITE_RIGHTS = (1 << 1) | (1 << 14)

# Права записи в папке: запись и обрезка файлов, удаление, создание, перенос (биты 4–13).
_DIR_WRITE_RIGHTS = _FILE_WRITE_RIGHTS | sum(1 << bit for bit in range(4, 14))

# Наименьшая версия Landlock с ограничением сигналов.
MINIMAL_ABI_VERSION = 6

# Ключ пути записи и разделитель перед программой в аргументах запуска.
WRITE_OPTION = "--write"
PROGRAM_SEPARATOR = "--"


class _RulesetAttr(ctypes.Structure):
    """Что ограничивает набор правил: доступ к файлам, к сети, области процессов."""

    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


class _PathBeneathAttr(ctypes.Structure):
    """Правило: разрешённый доступ внутри папки или к файлу."""

    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def landlock_abi_version() -> int:
    """
    Узнаёт версию Landlock в ядре.

    Возвращает: Версию Landlock; 0, если Landlock недоступен.
    """
    libc = ctypes.CDLL(None, use_errno = True)
    version = libc.syscall(_CREATE_RULESET_SYSCALL, None, 0, _CREATE_RULESET_VERSION)

    return max(version, 0)


def restrict_self(*, write_paths: list[str]) -> None:
    """
    Ставит на текущий процесс Landlock: запись только в write_paths, сигналы только внутри песочницы.

        write_paths: папки и файлы, куда разрешена запись; несуществующие пропускаются.
    """
    libc = ctypes.CDLL(None, use_errno = True)
    attr = _RulesetAttr(_DIR_WRITE_RIGHTS, 0, _SCOPE_SIGNAL)
    ruleset_fd = libc.syscall(_CREATE_RULESET_SYSCALL, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    _check(result = ruleset_fd, action = "создать набор правил")

    for path in write_paths:
        if not os.path.exists(path):
            continue

        rights = _DIR_WRITE_RIGHTS if os.path.isdir(path) else _FILE_WRITE_RIGHTS
        path_fd = os.open(path, os.O_PATH)
        try:
            rule = _PathBeneathAttr(rights, path_fd)
            _check(
                result = libc.syscall(_ADD_RULE_SYSCALL, ruleset_fd, _RULE_PATH_BENEATH, ctypes.byref(rule), 0),
                action = f"добавить правило для {path}",
            )
        finally:
            os.close(path_fd)

    _check(result = libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), action = "запретить повышение прав")
    _check(result = libc.syscall(_RESTRICT_SELF_SYSCALL, ruleset_fd, 0), action = "включить ограничения")
    os.close(ruleset_fd)


def _check(*, result: int, action: str) -> None:
    """
    Прерывает запуск, если системный вызов вернул ошибку.

        result: результат системного вызова.
        action: что делал вызов, для текста ошибки.
    """
    if result < 0:
        raise OSError(ctypes.get_errno(), f"Landlock: не удалось {action}: {os.strerror(ctypes.get_errno())}")


def _parse_arguments(*, arguments: list[str]) -> tuple[list[str], list[str]]:
    """
    Разбирает аргументы запуска.

        arguments: аргументы после имени программы.

    Возвращает: Пути записи и программу с аргументами.
    """
    separator_index = arguments.index(PROGRAM_SEPARATOR)
    options = arguments[:separator_index]
    write_paths = [options[index + 1] for index, option in enumerate(options) if option == WRITE_OPTION]

    return write_paths, arguments[separator_index + 1:]


if __name__ == "__main__":
    paths, program = _parse_arguments(arguments = sys.argv[1:])
    restrict_self(write_paths = paths)
    os.execvp(program[0], program)
