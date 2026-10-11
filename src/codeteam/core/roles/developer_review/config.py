"""Описание роли приёмщика этапа: промпт, модель, инструменты, помощник с браузером, хуки, проверки сдачи."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.agent.workspace import CHECK_DIR, CONTEXT_FILE_NAME
from codeteam.core.roles.browser_checker import build_check_in_browser_tool
from codeteam.core.roles.common import ACCEPTED_VERDICT, PROJECT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    RoleSettings, check_verdict_file, clean_project_check, tracked_changes_check, verdict_line_hook
from codeteam.core.roles.developer_review.prompts import TRACKED_CHANGES_REMARK
from codeteam.core.tools.shell import START_SERVICE_TOOL_NAME, STOP_PROCESS_TOOL_NAME

DEVELOPER_REVIEW_ROLE = RoleSettings(
    name = "developer_review",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "check_dir": CHECK_DIR.as_posix(),
        "context_file": CONTEXT_FILE_NAME,
        "start_service_tool": START_SERVICE_TOOL_NAME,
        "stop_process_tool": STOP_PROCESS_TOOL_NAME,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (VERDICT_FILE_NAME,), only_answer_files = False),
        draft_phase_hint_hook,
        verdict_line_hook,
        tracked_changes_check(remark = TRACKED_CHANGES_REMARK),
    ),
    answer_checks = (check_verdict_file, clean_project_check),
    helper_tools = (build_check_in_browser_tool,),
    mcp_servers = (),
)
