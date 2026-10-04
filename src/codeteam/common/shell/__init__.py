"""Запуск команд оболочки."""

from codeteam.common.shell.command import CommandResult, run_command
from codeteam.common.shell.macos_sandbox import ReadRestrictions

__all__ = ["CommandResult", "ReadRestrictions", "run_command"]
