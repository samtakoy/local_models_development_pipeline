"""Описание роли сеньора: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import code_block_hook, draft_phase_hint_hook, private_file_hook, \
    readonly_work_phase_hint_hook
from codeteam.core.agent.workspace import DRAFT_DIR_NAME
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.senior.prompts import SENIOR_CODE_BLOCK_REMARK

# Наибольшее число строк в одном блоке кода с указанным языком в плане сеньора.
SENIOR_CODE_BLOCK_LINE_LIMIT = 30

# Файлы ответа роли в черновике.
SENIOR_ANSWER_FILES = AnswerFiles(names = (), only_these = False)

SENIOR_ROLE = RoleSettings(
    name = "senior",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = PROJECT_TOOL_NAMES,
    answer_files = SENIOR_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = SENIOR_ANSWER_FILES),
        draft_phase_hint_hook,
        readonly_work_phase_hint_hook,
        code_block_hook(
            folder = Path(DRAFT_DIR_NAME),
            max_lines = SENIOR_CODE_BLOCK_LINE_LIMIT,
            remark = SENIOR_CODE_BLOCK_REMARK,
            skip_file_names = (),
        ),
    ),
    answer_checks = (),
    helper_tools = (),
    mcp_servers = (),
)
