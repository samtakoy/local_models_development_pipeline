"""Описание роли помощника с браузером: промпт, модель, инструменты, сервер браузера, инструмент смотреть
скриншоты, подсказка к отказу по пути, проверка сдачи, файл ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.browser_checker.hooks import browser_checker_refusal_hook
from codeteam.core.roles.common import DRAFT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.common.browser import playwright_server
from codeteam.core.roles.picture_viewer import DESCRIBE_PICTURE_TOOL_NAME, build_describe_picture_tool

# Файл ответа помощника в его черновике: целиком возвращается спросившему агенту.
OBSERVATIONS_FILE_NAME = "000_observations.md"

BROWSER_CHECKER_ROLE = RoleSettings(
    name = "bro_check",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "observations_file": OBSERVATIONS_FILE_NAME,
        "check_dir": CHECK_DIR.as_posix(),
        "describe_picture_tool": DESCRIBE_PICTURE_TOOL_NAME,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.NONE,
    tool_names = DRAFT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (OBSERVATIONS_FILE_NAME,), only_answer_files = True),
        draft_phase_hint_hook,
        browser_checker_refusal_hook,
    ),
    answer_checks = (required_files_check(file_names = (OBSERVATIONS_FILE_NAME,)),),
    helper_tools = (build_describe_picture_tool,),
    mcp_servers = (playwright_server,),
)
