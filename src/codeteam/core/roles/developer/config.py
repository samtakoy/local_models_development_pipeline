"""Описание роли разработчика: промпт, модель, инструменты, хуки, помощники: советник и помощник с браузером."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.step_hooks import draft_phase_hint_hook, private_file_hook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.advisor import QUERY_LIBRARY_DOCS_TOOL_NAME, build_query_library_docs_tool
from codeteam.core.roles.browser_checker import build_check_in_browser_tool
from codeteam.core.roles.common import PROJECT_TOOL_NAMES, RoleSettings

# Файлы ответа роли в черновике.
DEVELOPER_ANSWER_FILES = AnswerFiles(names = (), only_these = False)

DEVELOPER_ROLE = RoleSettings(
    name = "developer",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {"check_dir": CHECK_DIR.as_posix(), "query_library_docs_tool": QUERY_LIBRARY_DOCS_TOOL_NAME},
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    answer_files = DEVELOPER_ANSWER_FILES,
    step_hooks = (
        private_file_hook(answer_files = DEVELOPER_ANSWER_FILES),
        draft_phase_hint_hook,
    ),
    answer_checks = (),
    helper_tools = (build_query_library_docs_tool, build_check_in_browser_tool),
    mcp_servers = (),
)
