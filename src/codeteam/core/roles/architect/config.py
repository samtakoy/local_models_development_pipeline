"""Описание роли архитектора: промпт, модель, инструменты, хуки, файлы черновика."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.step_hooks import code_block_hook
from codeteam.core.roles.architect.prompts import ARCHITECT_CODE_BLOCK_REMARK
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

# Файл общего решения в черновике архитектора.
ARCHITECTURE_FILE_NAME = "000_architecture.md"

# Наибольшее число строк в одном блоке кода с указанным языком в черновике архитектора.
ARCHITECT_CODE_BLOCK_LINE_LIMIT = 10

ARCHITECT_ROLE = RoleSettings(
    name = "architect",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        code_block_hook(
            max_lines = ARCHITECT_CODE_BLOCK_LINE_LIMIT,
            remark = ARCHITECT_CODE_BLOCK_REMARK,
            skip_file_names = (ARCHITECTURE_FILE_NAME,),
        ),
    ),
    step_checks = (),
    answer_checks = (required_files_check(file_names = (ARCHITECTURE_FILE_NAME,)),),
)
