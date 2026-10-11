"""Описание роли советника: промпт, модель, инструменты, проверки сдачи, файл ответа."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

# Файл ответа советника в его черновике: целиком возвращается спросившему агенту.
ADVICE_FILE_NAME = "000_advice.md"

ADVISOR_ROLE = RoleSettings(
    name = "advisor",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"advice_file": ADVICE_FILE_NAME, "check_dir": CHECK_DIR.as_posix()},
    model_name = None,
    reasoning_level = ReasoningLevel.HIGH,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (
        private_file_hook(answer_file_names = (ADVICE_FILE_NAME,), only_answer_files = True),
        draft_phase_hint_hook,
    ),
    answer_checks = (required_files_check(file_names = (ADVICE_FILE_NAME,)),),
    helper_tools = (),
    mcp_servers = (),
)
