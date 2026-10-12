"""Описание роли разработчика: промпт, модель, инструменты, хуки, помощники: советник и помощник с браузером."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.advisor import LOOK_AT_DOCUMENTATION_TOOL_NAME, build_look_at_documentation_tool
from codeteam.core.roles.browser_checker import build_check_in_browser_tool
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

DEVELOPER_ROLE = RoleSettings(
    name = "developer",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"check_dir": CHECK_DIR.as_posix(), "look_at_documentation_tool": LOOK_AT_DOCUMENTATION_TOOL_NAME},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (), only_answer_files = False),
        draft_phase_hint_hook,
    ),
    answer_checks = (),
    helper_tools = (build_look_at_documentation_tool, build_check_in_browser_tool),
    mcp_servers = (),
)
