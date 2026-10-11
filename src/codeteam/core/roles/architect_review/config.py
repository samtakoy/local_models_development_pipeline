"""Описание роли ревьюера архитектора: промпт, модель, инструменты, хуки."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook, readonly_work_phase_hint_hook
from codeteam.core.roles.common import ACCEPTED_VERDICT, PROJECT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    RoleSettings, check_verdict_file, verdict_line_hook

ARCHITECT_REVIEW_ROLE = RoleSettings(
    name = "architect_review",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (VERDICT_FILE_NAME,), only_answer_files = False),
        draft_phase_hint_hook,
        readonly_work_phase_hint_hook,
        verdict_line_hook,
    ),
    answer_checks = (check_verdict_file,),
    helper_tools = (),
    mcp_servers = (),
)
