"""Описание роли менеджера продукта: промпт, модель, инструменты, хуки, файлы черновика."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.roles.common import DRAFT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.picture_viewer import DESCRIBE_PICTURE_TOOL_NAME, build_describe_picture_tool

# Файл чеклиста требований в черновике менеджера продукта.
REQUIREMENTS_FILE_NAME = "100_requirements.md"

PM_ROLE = RoleSettings(
    name = "pm",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"requirements_file": REQUIREMENTS_FILE_NAME, "describe_picture_tool": DESCRIBE_PICTURE_TOOL_NAME},
    model_name = None,
    reasoning_level = ReasoningLevel.HIGH,
    tool_names = DRAFT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (REQUIREMENTS_FILE_NAME,), only_answer_files = False),
        draft_phase_hint_hook,
    ),
    answer_checks = (required_files_check(file_names = (REQUIREMENTS_FILE_NAME,)),),
    helper_tools = (build_describe_picture_tool,),
    mcp_servers = (),
)
