"""Сервер документации Context7 MCP для советника: поиск библиотеки и запрос к её документации."""

from pathlib import Path

from codeteam.core.roles.common import CallerContext
from codeteam.core.tools.mcp import McpServer

# Пакет Context7 MCP с закреплённой версией: запускается через npx.
CONTEXT7_MCP_PACKAGE = "@upstash/context7-mcp@4.1.1"

# Программа запуска сервера.
CONTEXT7_COMMAND = "npx"

# Аргументы запуска: -y — скачать пакет без вопроса.
CONTEXT7_ARGS = ("-y", CONTEXT7_MCP_PACKAGE)

# Инструмент сервера: найти библиотеку по имени и получить её идентификатор Context7.
RESOLVE_LIBRARY_TOOL_NAME = "resolve-library-id"

# Инструмент сервера: запрос к документации библиотеки по её идентификатору.
QUERY_DOCS_TOOL_NAME = "query-docs"


def context7_server(caller_context: CallerContext) -> McpServer:
    """
    Собирает сервер Context7 MCP для запуска советника.

        caller_context: агент, которому нужна документация.

    Возвращает: Сервер MCP: работает в папке проекта, вызовы не проверяются.
    """
    return McpServer(
        name = "context7",
        command = CONTEXT7_COMMAND,
        args = CONTEXT7_ARGS,
        cwd = Path(caller_context.cfg.project_path),
        check_call = None,
        excluded_tool_names = (),
    )
