"""Описание роли разработчика: промпт, модель, инструменты, хуки, помощники."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.advisor import build_get_advice_tool
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

DEVELOPER_ROLE = RoleSettings(
    name = "developer",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"check_dir": CHECK_DIR.as_posix()},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (),
    step_checks = (),
    answer_checks = (),
    helper_tools = (build_get_advice_tool,),
    mcp_servers = (),
)
