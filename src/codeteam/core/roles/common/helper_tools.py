"""Инструменты вызова другого агента: что нужно знать сборщику такого инструмента о вызывающем агенте."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import BaseTool

from codeteam.core.pipeline.state import PipelineConfig


@dataclass(frozen = True)
class HelperContext:
    """
    Вызывающий агент, для которого собирается инструмент вызова другого агента.

        cfg: настройки запуска пайплайна.
        caller_name: имя роли вызывающего агента.
        caller_private_dir_name: путь личной папки вызывающего агента внутри папки личных папок;
            личные папки помощников лежат внутри неё.
        caller_journal_name: имя журнала вызывающего агента без расширения; журналы помощников
            называются от него.
    """

    cfg: PipelineConfig
    caller_name: str
    caller_private_dir_name: Path
    caller_journal_name: str


# Сборщик инструмента вызова другого агента: вызывающий агент → инструмент.
HelperToolBuilder = Callable[[HelperContext], BaseTool]
