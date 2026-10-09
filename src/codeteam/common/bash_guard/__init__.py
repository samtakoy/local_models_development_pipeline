"""Разбор команд bash на простые команды: имя и аргументы."""

from codeteam.common.bash_guard.parse import SimpleCommand, Word, parse_command

__all__ = ["SimpleCommand", "Word", "parse_command"]
