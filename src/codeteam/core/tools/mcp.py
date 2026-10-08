"""
Инструменты серверов MCP для синхронного агента.

Инструменты MCP работают только асинхронно, а граф агента вызывает инструменты синхронно.
Сессии серверов живут в отдельном потоке со своим циклом событий; каждый инструмент MCP
оборачивается в синхронный, который передаёт вызов в этот поток и ждёт ответа.
"""

import asyncio
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

# Предел ожидания запуска серверов MCP, секунды.
MCP_START_TIMEOUT_SECONDS = 120

# Предел ожидания одного вызова инструмента MCP, секунды.
MCP_CALL_TIMEOUT_SECONDS = 120


@dataclass(frozen = True)
class McpServer:
    """
    Сервер MCP, который запускается командой и говорит через stdin и stdout.

        name: имя сервера.
        command: программа запуска.
        args: аргументы программы.
    """

    name: str
    command: str
    args: tuple[str, ...]


class McpTools:
    """
    Открытые сессии серверов MCP и их синхронные инструменты; используется как контекстный менеджер.
    """

    def __init__(self, *, servers: tuple[McpServer, ...]) -> None:
        self._servers = servers
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._tools: list[BaseTool] = []
        self._error: BaseException | None = None
        self._thread = threading.Thread(target = self._run, name = "mcp", daemon = True)

    def __enter__(self) -> list[BaseTool]:
        """
        Запускает серверы и открывает их сессии.

        Возвращает: Синхронные инструменты всех серверов.
        """
        if not self._servers:
            return []

        self._thread.start()
        if not self._ready.wait(timeout = MCP_START_TIMEOUT_SECONDS):
            raise TimeoutError(f"серверы MCP не запустились за {MCP_START_TIMEOUT_SECONDS} с")
        if self._error is not None:
            raise RuntimeError(f"серверы MCP не запустились: {self._error}") from self._error

        return [self._sync_tool(tool = tool) for tool in self._tools]

    def __exit__(self, *exception_info) -> None:
        """
        Закрывает сессии и останавливает серверы.
        """
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread.is_alive():
            self._thread.join(timeout = MCP_START_TIMEOUT_SECONDS)

    def _run(self) -> None:
        """
        Тело потока: цикл событий, в котором живут сессии серверов.
        """
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        """
        Открывает сессии серверов, загружает инструменты и держит сессии до сигнала остановки.
        """
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        client = MultiServerMCPClient({
            server.name: {"command": server.command, "args": list(server.args), "transport": "stdio"}
            for server in self._servers
        })
        try:
            async with AsyncExitStack() as stack:
                for server in self._servers:
                    session = await stack.enter_async_context(client.session(server.name))
                    self._tools.extend(await load_mcp_tools(session))
                self._ready.set()
                await self._stop.wait()
        except BaseException as error:
            self._error = error
            self._ready.set()

    def _sync_tool(self, *, tool: BaseTool) -> BaseTool:
        """
        Оборачивает асинхронный инструмент MCP в синхронный с тем же именем, описанием и аргументами.

            tool: инструмент MCP.

        Возвращает: Синхронный инструмент.
        """

        def call(**arguments):
            """
            Передаёт вызов в поток сессий и ждёт ответа.

                arguments: аргументы вызова.

            Возвращает: Ответ инструмента MCP.
            """
            future = asyncio.run_coroutine_threadsafe(tool.ainvoke(arguments), self._loop)

            return future.result(timeout = MCP_CALL_TIMEOUT_SECONDS)

        return StructuredTool.from_function(
            func = call,
            name = tool.name,
            description = tool.description,
            args_schema = tool.args_schema,
            handle_tool_error = True,
        )
