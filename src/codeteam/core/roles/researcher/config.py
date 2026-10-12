"""Описание роли исследователя: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook, readonly_work_phase_hint_hook
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

# Файлы ответа роли в черновике.
RESEARCHER_ANSWER_FILES = AnswerFiles(names = (), only_these = False)

RESEARCHER_ROLE = RoleSettings(
    name = "researcher",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = PROJECT_TOOL_NAMES,
    answer_files = RESEARCHER_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = RESEARCHER_ANSWER_FILES),
        draft_phase_hint_hook,
        readonly_work_phase_hint_hook,
    ),
    answer_checks = (),
    helper_tools = (),
    mcp_servers = (),
)
