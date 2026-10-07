"""Роль агента: настройки, с которыми пайплайн запускает агента."""

from dataclasses import dataclass

from codeteam.common.llm import ReasoningLevel


@dataclass(frozen = True)
class AgentRole:
    """
    Настройки роли агента.

        name: имя роли; по нему назван агент в журнале.
        system_prompt: промпт роли: кто агент и как решает задачу.
        model_name: модель агента.
        reasoning_level: уровень размышления модели агента.
        tool_names: имена инструментов агента, одни и те же в фазе работы и в фазе черновика.
    """

    name: str
    system_prompt: str
    model_name: str
    reasoning_level: ReasoningLevel
    tool_names: tuple[str, ...]
