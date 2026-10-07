"""Роль агента: настройки, с которыми пайплайн запускает агента."""

from dataclasses import dataclass


@dataclass(frozen = True)
class AgentRole:
    """
    Настройки роли агента.

        name: имя роли; по нему назван агент в журнале.
        system_prompt: промпт роли: кто агент и как решает задачу.
        model_name: модель агента.
        tool_names: имена инструментов агента, одни и те же в фазе работы и в фазе черновика.
    """

    name: str
    system_prompt: str
    model_name: str
    tool_names: tuple[str, ...]
