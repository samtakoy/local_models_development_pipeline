"""Клиент модели: сборка клиента ollama, режимы работы, уровень размышления."""

from codeteam.common.llm.client import OllamaConfig, build_chat_model, describe_chat_model
from codeteam.common.llm.profiles import GenerationMode
from codeteam.common.llm.reasoning import ReasoningLevel

__all__ = [
    "GenerationMode",
    "OllamaConfig",
    "ReasoningLevel",
    "build_chat_model",
    "describe_chat_model",
]
