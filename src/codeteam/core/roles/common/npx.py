"""Запуск пакетов npm командой npx со своим кэшем npm."""

from pathlib import Path

# Программа запуска пакетов npm.
NPX_COMMAND = "npx"


def npx_args(*, npm_cache_dir: Path, package_args: tuple[str, ...]) -> tuple[str, ...]:
    """
    Строит аргументы npx: свой кэш npm, затем пакет и его аргументы.

        npm_cache_dir: папка кэша npm.
        package_args: пакет и его аргументы, с флагами npx перед пакетом.

    Возвращает: Аргументы программы NPX_COMMAND.
    """
    return ("--cache", str(npm_cache_dir), *package_args)
