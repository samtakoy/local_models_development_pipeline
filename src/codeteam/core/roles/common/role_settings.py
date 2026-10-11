"""Описание роли: всё, что роль решает про себя сама, и наборы инструментов ролей."""

from dataclasses import dataclass
from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.step_hooks import StepHook
from codeteam.core.roles.common.external_tools import HelperToolBuilder, McpServerBuilder
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, GLOB_TOOL_NAME, GREP_TOOL_NAME, \
    READ_TOOL_NAME, WRITE_TOOL_NAME
from codeteam.core.tools.shell import BASH_TOOL_NAME, START_SERVICE_TOOL_NAME, STOP_PROCESS_TOOL_NAME

# Инструменты ролей, которые работают с кодом проекта.
PROJECT_TOOL_NAMES = (
    READ_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
    BASH_TOOL_NAME,
    START_SERVICE_TOOL_NAME,
    STOP_PROCESS_TOOL_NAME,
)

# Инструменты ролей, которые работают только со своим черновиком.
DRAFT_TOOL_NAMES = (
    READ_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
)


@dataclass(frozen = True)
class RoleSettings:
    """
    Описание роли.

        name: имя роли: имя узла графа, личной папки и агента в журнале.
        system_prompt_path: файл системного промпта роли.
        prompt_fields: значения полей вида {имя поля} в тексте системного промпта.
        model_name: модель агента; None — модель пайплайна.
        reasoning_level: уровень размышления модели агента.
        tool_names: имена инструментов агента.
        step_hooks: хуки шага инструментов: замечания к изменённым файлам личной папки и к проекту.
        answer_checks: проверки сдачи: замечания к черновику, когда агент отвечает DONE.
        answer_file_names: заранее известные имена файлов ответа роли в черновике.
        only_answer_files: в черновике роли разрешены только файлы ответа.
        work_refusal_hints: пояснения к отказу по пути в фазе работы: одно, выбранное по пути;
            пустой кортеж — без пояснения.
        helper_tools: сборщики инструментов вызова другого агента, например советника.
        mcp_servers: сборщики серверов MCP, чьи инструменты получает агент; сессии открыты, пока агент работает.
    """

    name: str
    system_prompt_path: Path
    prompt_fields: dict[str, str]
    model_name: str | None
    reasoning_level: ReasoningLevel
    tool_names: tuple[str, ...]
    step_hooks: tuple[StepHook, ...]
    answer_checks: tuple[AnswerCheck, ...]
    answer_file_names: tuple[str, ...]
    only_answer_files: bool
    work_refusal_hints: tuple[str, ...]
    helper_tools: tuple[HelperToolBuilder, ...]
    mcp_servers: tuple[McpServerBuilder, ...]
