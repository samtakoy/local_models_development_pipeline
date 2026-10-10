"""Роль помощника с браузером: проходит сценарии в запущенном приложении по просьбе агента; вызывается
инструментом check_in_browser."""

from codeteam.core.roles.browser_checker.config import BROWSER_CHECKER_ROLE, OBSERVATIONS_FILE_NAME
from codeteam.core.roles.browser_checker.tool import CHECK_IN_BROWSER_TOOL_NAME, build_check_in_browser_tool

__all__ = [
    "BROWSER_CHECKER_ROLE",
    "CHECK_IN_BROWSER_TOOL_NAME",
    "OBSERVATIONS_FILE_NAME",
    "build_check_in_browser_tool",
]
