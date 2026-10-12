"""Описание роли итоговой приёмки: промпт, модель, инструменты, хуки, проверки сдачи, файлы ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.roles.acceptance.checks import FIX_PLAN_FILE_NAME, fix_plan_check
from codeteam.core.roles.common import ACCEPTED_VERDICT, DRAFT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    RoleSettings, check_verdict_file, verdict_line_hook

# Файлы ответа роли в черновике.
ACCEPTANCE_ANSWER_FILES = AnswerFiles(names = (VERDICT_FILE_NAME, FIX_PLAN_FILE_NAME), only_these = True)

ACCEPTANCE_ROLE = RoleSettings(
    name = "acceptance",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "plan_file": FIX_PLAN_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = DRAFT_TOOL_NAMES,
    answer_files = ACCEPTANCE_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = ACCEPTANCE_ANSWER_FILES),
        draft_phase_hint_hook,
        verdict_line_hook,
    ),
    answer_checks = (check_verdict_file, fix_plan_check),
    helper_tools = (),
    mcp_servers = (),
)
