"""Описание роли исследователя: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

RESEARCHER_ROLE = RoleSettings(
    name = "researcher",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {},
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (), only_answer_files = False),
        draft_phase_hint_hook,
    ),
    answer_checks = (),
    helper_tools = (),
    mcp_servers = (),
)
