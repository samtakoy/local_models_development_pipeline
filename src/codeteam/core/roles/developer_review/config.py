"""Описание роли приёмщика этапа: промпт, модель, инструменты, хуки, проверки сдачи."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common import ACCEPTED_VERDICT, PROJECT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    RoleSettings, check_verdict_file

DEVELOPER_REVIEW_ROLE = RoleSettings(
    name = "developer_review",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "check_dir": CHECK_DIR.as_posix(),
    },
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (),
    step_checks = (),
    answer_checks = (check_verdict_file,),
    helper_tools = (),
)
