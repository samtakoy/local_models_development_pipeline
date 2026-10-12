"""Описание роли проверки по сценариям: промпт оценщика, модель, инструменты, хуки, проверки сдачи, файлы ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.roles.common import ACCEPTED_VERDICT, DRAFT_TOOL_NAMES, REPORT_FILE_NAME, REWORK_VERDICT, \
    VERDICT_FILE_NAME, RoleSettings, check_verdict_file, verdict_line_hook
from codeteam.core.roles.web_scenarios_tester.runner import LAUNCH_FAILED_FILE_NAME

# Файлы ответа роли в черновике.
WEB_SCENARIOS_TESTER_ANSWER_FILES = AnswerFiles(names = (VERDICT_FILE_NAME, REPORT_FILE_NAME), only_these = True)

WEB_SCENARIOS_TESTER_ROLE = RoleSettings(
    name = "web_scenarios_tester",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "report_file": REPORT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "launch_failed_file": LAUNCH_FAILED_FILE_NAME,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = DRAFT_TOOL_NAMES,
    answer_files = WEB_SCENARIOS_TESTER_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = WEB_SCENARIOS_TESTER_ANSWER_FILES),
        draft_phase_hint_hook,
        verdict_line_hook,
    ),
    answer_checks = (check_verdict_file, required_files_check(file_names = WEB_SCENARIOS_TESTER_ANSWER_FILES.names)),
    helper_tools = (),
    mcp_servers = (),
)
