"""Описание роли сеньора: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import code_block_hook
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.senior.prompts import SENIOR_CODE_BLOCK_REMARK

# Наибольшее число строк в одном блоке кода с указанным языком в плане сеньора.
SENIOR_CODE_BLOCK_LINE_LIMIT = 30

SENIOR_ROLE = RoleSettings(
    name = "senior",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        code_block_hook(
            max_lines = SENIOR_CODE_BLOCK_LINE_LIMIT,
            remark = SENIOR_CODE_BLOCK_REMARK,
            skip_file_names = (),
        ),
    ),
    step_checks = (),
    answer_checks = (),
)
