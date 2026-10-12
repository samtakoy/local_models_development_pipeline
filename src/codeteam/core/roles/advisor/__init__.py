"""Роль советника по документации: ответ на вопрос агента по документации библиотек; вызывается инструментом
look_at_documentation."""

from codeteam.core.roles.advisor.config import ADVICE_FILE_NAME, ADVISOR_ROLE
from codeteam.core.roles.advisor.tool import LOOK_AT_DOCUMENTATION_TOOL_NAME, build_look_at_documentation_tool

__all__ = [
    "ADVICE_FILE_NAME",
    "ADVISOR_ROLE",
    "LOOK_AT_DOCUMENTATION_TOOL_NAME",
    "build_look_at_documentation_tool",
]
