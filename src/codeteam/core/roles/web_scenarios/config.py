"""Описание роли составителя сценариев: промпт, модель, инструменты, хуки, проверка сдачи, файлы ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook, readonly_work_phase_hint_hook
from codeteam.core.roles.common import RoleSettings
from codeteam.core.roles.web_scenarios.checks import scenarios_check
from codeteam.core.roles.web_scenarios.launch import LAUNCH_FILE_NAME
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, GLOB_TOOL_NAME, GREP_TOOL_NAME, \
    READ_TOOL_NAME, WRITE_TOOL_NAME

# Инструменты составителя сценариев: чтение проекта и запись своего черновика, без команд.
WEB_SCENARIOS_TOOL_NAMES = (
    READ_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
)

# Файлы ответа роли в черновике.
WEB_SCENARIOS_ANSWER_FILES = AnswerFiles(names = (LAUNCH_FILE_NAME,), only_these = False)

WEB_SCENARIOS_ROLE = RoleSettings(
    name = "web_scenarios",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"launch_file": LAUNCH_FILE_NAME},
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = WEB_SCENARIOS_TOOL_NAMES,
    answer_files = WEB_SCENARIOS_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = WEB_SCENARIOS_ANSWER_FILES),
        draft_phase_hint_hook,
        readonly_work_phase_hint_hook,
    ),
    answer_checks = (scenarios_check,),
    helper_tools = (),
    mcp_servers = (),
)
