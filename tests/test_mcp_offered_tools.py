"""Тесты отбора инструментов сервера MCP: исключённые инструменты агент не получает."""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from codeteam.core.tools.mcp import McpServer, offered_tools


def _tool(*, name: str) -> BaseTool:
    """
    Собирает инструмент с заданным именем.

        name: имя инструмента.

    Возвращает: Инструмент.
    """
    return StructuredTool.from_function(func = lambda: "", name = name, description = name)


def _server(*, excluded_tool_names: tuple[str, ...]) -> McpServer:
    """
    Собирает описание сервера с исключёнными инструментами.

        excluded_tool_names: имена исключённых инструментов.

    Возвращает: Описание сервера.
    """
    return McpServer(
        name = "test",
        command = "test",
        args = (),
        cwd = Path("."),
        env = {},
        check_call = None,
        excluded_tool_names = excluded_tool_names,
    )


def test_excluded_tools_are_not_offered() -> None:
    """
    Исключённый инструмент убран, остальные остались в прежнем порядке.
    """
    tools = [_tool(name = name) for name in ("browser_click", "browser_run_code_unsafe", "browser_snapshot")]

    offered = offered_tools(server = _server(excluded_tool_names = ("browser_run_code_unsafe",)), tools = tools)

    assert [tool.name for tool in offered] == ["browser_click", "browser_snapshot"]


def test_no_exclusions_offers_all_tools() -> None:
    """
    Без исключений агент получает все инструменты сервера.
    """
    tools = [_tool(name = name) for name in ("browser_click", "browser_snapshot")]

    assert offered_tools(server = _server(excluded_tool_names = ()), tools = tools) == tools
