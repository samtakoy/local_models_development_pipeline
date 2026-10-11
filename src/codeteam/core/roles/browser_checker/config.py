"""Описание роли помощника с браузером: промпт, модель, инструменты, сервер браузера, подсказка к отказу по пути,
проверка сдачи, файл ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.statistics import WORK_PHASE
from codeteam.core.agent.step_hooks import refusal_hint_hook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.browser_checker.prompts import BROWSER_CHECKER_REFUSAL_HINTS
from codeteam.core.roles.common import DRAFT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.common.browser import playwright_server

# Файл ответа помощника в его черновике: целиком возвращается спросившему агенту.
OBSERVATIONS_FILE_NAME = "000_observations.md"

BROWSER_CHECKER_ROLE = RoleSettings(
    name = "bro_check",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"observations_file": OBSERVATIONS_FILE_NAME, "check_dir": CHECK_DIR.as_posix()},
    model_name = None,
    reasoning_level = ReasoningLevel.MEDIUM,
    tool_names = DRAFT_TOOL_NAMES,
    step_hooks = (refusal_hint_hook(phase = WORK_PHASE, hints = BROWSER_CHECKER_REFUSAL_HINTS),),
    answer_checks = (required_files_check(file_names = (OBSERVATIONS_FILE_NAME,)),),
    answer_file_names = (OBSERVATIONS_FILE_NAME,),
    only_answer_files = True,
    helper_tools = (),
    mcp_servers = (playwright_server,),
)
