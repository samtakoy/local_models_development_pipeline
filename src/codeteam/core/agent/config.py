from dataclasses import dataclass

from langchain_core.runnables import Runnable


@dataclass(frozen = True)
class AgentConfig:
    system_prompt: str
    task: str
    # BaseChatModel
    chat_model: Runnable
    # имя инструмента и аргументы - вызываются на этапе инициализации агента
    warmup_calls: list[tuple[str, dict]]