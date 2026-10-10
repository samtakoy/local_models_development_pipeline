"""Внешние инструменты агента: помощники-агенты и серверы MCP, которые собираются под конкретный запуск."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import BaseTool

from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.tools.mcp import McpServer


@dataclass(frozen = True)
class CallerContext:
    """
    Агент, для которого собираются внешние инструменты.

        cfg: настройки запуска пайплайна.
        caller_name: имя роли агента.
        caller_private_dir_name: путь личной папки агента внутри папки личных папок;
            личные папки помощников лежат внутри неё.
        caller_journal_name: имя журнала агента без расширения; журналы помощников и вывод серверов MCP
            называются от него.
    """

    cfg: PipelineConfig
    caller_name: str
    caller_private_dir_name: Path
    caller_journal_name: str


# Сборщик инструмента-помощника: агент → инструмент; None - инструмент в этом запуске недоступен,
# например не задана нужная ему модель.
HelperToolBuilder = Callable[[CallerContext], BaseTool | None]

# Сборщик сервера MCP: агент → описание сервера, аргументы которого зависят от запуска.
McpServerBuilder = Callable[[CallerContext], McpServer]
