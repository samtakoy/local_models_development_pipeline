"""Инструмент query_library_docs: агент спрашивает советника по документации — отдельного агента со свежей
памятью, который ищет ответ в документации библиотек."""

import itertools
import logging
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.core.agent.workspace import helpers_dir
from codeteam.core.roles.advisor.config import ADVICE_FILE_NAME, ADVISOR_ROLE
from codeteam.core.roles.advisor.prompts import (
    ADVICE_LIMIT_ERROR,
    ADVISOR_FAILED_ERROR,
    ADVICE_TRUNCATED_NOTE,
    ADVISOR_TASK,
    CONTEXT_NOT_GIVEN,
    QUERY_LIBRARY_DOCS_CONTEXT_DESCRIPTION,
    QUERY_LIBRARY_DOCS_DESCRIPTION,
    QUERY_LIBRARY_DOCS_QUESTION_DESCRIPTION,
    NO_ADVICE_ERROR,
)
from codeteam.core.roles.common import CallerContext, reserve_private_dir_name, run_role

logger = logging.getLogger(__name__)

# Имя инструмента вызова советника по документации.
QUERY_LIBRARY_DOCS_TOOL_NAME = "query_library_docs"

# Наибольшее число вызовов советника за одну работу агента: защита от зацикливания.
ADVICE_CALL_LIMIT = 30

# Наибольшая длина ответа советника, которая возвращается в историю агента, знаков.
ADVICE_LENGTH_LIMIT = 10000


class QueryLibraryDocsArguments(BaseModel):
    """
    Аргументы query_library_docs.
    """

    question: str = Field(description = QUERY_LIBRARY_DOCS_QUESTION_DESCRIPTION)
    context: str | None = Field(default = None, description = QUERY_LIBRARY_DOCS_CONTEXT_DESCRIPTION)


def build_query_library_docs_tool(caller_context: CallerContext) -> BaseTool | None:
    """
    Собирает инструмент query_library_docs для вызывающего агента.

    Каждый вызов запускает советника в своей личной папке внутри папки помощников вызывающего агента:
    <папка вызывающего>_help/advisor_r<номер>; журнал советника — <журнал вызывающего>.advisor_r<номер>.
    Проект советнику закрыт: он видит только свою личную папку и документацию Context7.

        caller_context: агент, который будет спрашивать совета.

    Возвращает: Инструмент query_library_docs; None, если советник по документации выключен в файле состава.
    """
    if not caller_context.cfg.library_docs:
        return None

    project_dir = Path(caller_context.cfg.project_path).resolve()
    # номера вызовов для предела ADVICE_CALL_LIMIT: next() выдаёт номер атомарно
    call_numbers = itertools.count(1)

    def query_library_docs(*, question: str, context: str | None = None) -> str:
        """
        Запускает советника на вопросе и возвращает его ответ.

            question: вопрос.
            context: что спросивший уже знает и пробовал; None — не указан.

        Возвращает: Ответ советника; длиннее ADVICE_LENGTH_LIMIT — начало ответа и путь к файлу.
            Ошибку для агента поднимает ToolException.
        """
        call_number = next(call_numbers)
        if call_number > ADVICE_CALL_LIMIT:
            raise ToolException(ADVICE_LIMIT_ERROR.format(limit = ADVICE_CALL_LIMIT))

        private_dir_name = reserve_private_dir_name(
            project_dir = project_dir,
            parent = helpers_dir(private_dir = caller_context.caller_private_dir_name),
            role_name = ADVISOR_ROLE.name,
            preserve_draft = False,
            preserve_context = False,
        )
        try:
            advice_dir = run_role(
                cfg = caller_context.cfg,
                role = ADVISOR_ROLE,
                journal_name = f"{caller_context.caller_journal_name}.{private_dir_name.name}",
                task = ADVISOR_TASK.format(
                    caller_name = caller_context.caller_name,
                    question = question,
                    context = context or CONTEXT_NOT_GIVEN,
                ),
                input_dirs = (),
                private_dir_name = private_dir_name,
                extra_readable_dirs = (),
                extra_writable_dirs = (),
                extra_command_writable_dirs = (),
            )
        except Exception as error:
            # падение советника не прерывает спросившего: он получает ошибку и продолжает работу
            logger.error(f"[{QUERY_LIBRARY_DOCS_TOOL_NAME}] советник прервал работу: {type(error).__name__}: {error}")
            raise ToolException(ADVISOR_FAILED_ERROR.format(error = type(error).__name__)) from error
        advice_path = advice_dir / ADVICE_FILE_NAME
        if not advice_path.is_file():
            raise ToolException(NO_ADVICE_ERROR.format(draft_dir = advice_dir.relative_to(project_dir)))

        advice = advice_path.read_text(encoding = "utf-8", errors = "replace")
        if len(advice) <= ADVICE_LENGTH_LIMIT:
            return advice

        return (
            advice[:ADVICE_LENGTH_LIMIT]
            + "\n\n"
            + ADVICE_TRUNCATED_NOTE.format(length = len(advice), advice_file = advice_path.relative_to(project_dir))
        )

    return StructuredTool.from_function(
        func = query_library_docs,
        name = QUERY_LIBRARY_DOCS_TOOL_NAME,
        description = QUERY_LIBRARY_DOCS_DESCRIPTION,
        args_schema = QueryLibraryDocsArguments,
        handle_tool_error = True,
    )

