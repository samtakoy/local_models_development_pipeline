from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel


@dataclass(frozen = True)
class AgentConfig:
    system_prompt: str
    chat_model: BaseChatModel