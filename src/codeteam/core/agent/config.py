from dataclasses import dataclass
from pathlib import Path

from langchain_core.runnables import Runnable


@dataclass(frozen = True)
class AgentConfig:
    system_prompt: str
    task: str
    # BaseChatModel
    chat_model: Runnable
    # имя инструмента и аргументы - вызываются на этапе инициализации агента
    warmup_calls: list[tuple[str, dict]]
    # лимит входных токенов
    history_token_limit: int
    # потолок входных токенов, после которого фаза черновика включается и во время записи ответа
    history_token_hard_limit: int
    # предел сбросов истории агента в 0
    max_resets: int
    limit_notice: str
    reinit_notice: str

    project_dir: Path
    # путь к рабочей директории агента
    relative_private_dir: Path
