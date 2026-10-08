"""Описание роли исследователя: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

RESEARCHER_ROLE = RoleSettings(
    name = "researcher",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (),
    step_checks = (),
    answer_checks = (),
)
