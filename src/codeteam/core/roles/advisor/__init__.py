"""Роль советника по документации: ответ на вопрос агента по документации библиотек; вызывается инструментом
query_library_docs."""

from codeteam.core.roles.advisor.config import ADVICE_FILE_NAME, ADVISOR_ROLE
from codeteam.core.roles.advisor.tool import QUERY_LIBRARY_DOCS_TOOL_NAME, build_query_library_docs_tool

__all__ = [
    "ADVICE_FILE_NAME",
    "ADVISOR_ROLE",
    "QUERY_LIBRARY_DOCS_TOOL_NAME",
    "build_query_library_docs_tool",
]
