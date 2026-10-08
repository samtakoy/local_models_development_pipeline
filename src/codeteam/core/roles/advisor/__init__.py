"""Роль советника: ответ на вопрос застрявшего агента; вызывается инструментом get_advice."""

from codeteam.core.roles.advisor.config import ADVICE_FILE_NAME, ADVISOR_ROLE
from codeteam.core.roles.advisor.tool import GET_ADVICE_TOOL_NAME, build_get_advice_tool

__all__ = [
    "ADVICE_FILE_NAME",
    "ADVISOR_ROLE",
    "GET_ADVICE_TOOL_NAME",
    "build_get_advice_tool",
]
