from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable


@dataclass(frozen = True)
class AgentConfig:
    system_prompt: str
    task: str
    chat_model: Runnable # BaseChatModel