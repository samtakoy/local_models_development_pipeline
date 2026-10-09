"""Инструмент get_advice: агент спрашивает совета у советника — отдельного агента со свежей памятью."""

import itertools
import shutil
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.core.agent.workspace import CHECK_DIR, PRIVATE_ROOT
from codeteam.core.roles.advisor.config import ADVICE_FILE_NAME, ADVISOR_ROLE
from codeteam.core.roles.advisor.prompts import ADVISOR_TASK, GET_ADVICE_DESCRIPTION
from codeteam.core.roles.common import CallerContext, run_role

# Имя инструмента вызова советника.
GET_ADVICE_TOOL_NAME = "get_advice"

# Наибольшее число вызовов советника за одну работу агента: защита от зацикливания.
ADVICE_CALL_LIMIT = 30

# Наибольшая длина ответа советника, которая возвращается в историю агента, знаков.
ADVICE_LENGTH_LIMIT = 10000

# Папка внутри личной папки советника: копии файлов из личных папок, которые указал спросивший.
RELATED_DIR_NAME = "related"


class GetAdviceArguments(BaseModel):
    """
    Аргументы get_advice.
    """

    question: str = Field(description = "Задача, проблема, что уже пробовал, конкретный вопрос")
    context: str | None = Field(
        default = None,
        description = "контекст вопроса - дополнительное описание для понимания, из какой ситуации задано",
    )
    related_files: list[str] | None = Field(
        default = None,
        description = "Файлы, с которых советчику стоит начать (он может читать и другие)",
    )


def build_get_advice_tool(caller_context: CallerContext) -> BaseTool:
    """
    Собирает инструмент get_advice для вызывающего агента.

    Каждый вызов запускает советника в своей личной папке внутри личной папки вызывающего агента:
    <папка вызывающего>/advisor_<номер>; журнал советника — <журнал вызывающего>.advisor_<номер>.
    Проект советник читает; пишет, кроме черновика, только в папку временных скриптов CHECK_DIR.
    Файлы из личных папок, которые указал спросивший, советнику закрыты: он получает их копии.

        caller_context: агент, который будет спрашивать совета.

    Возвращает: Инструмент get_advice.
    """
    project_dir = Path(caller_context.cfg.project_path).resolve()
    # номера вызовов: next() выдаёт номер атомарно, параллельные вызовы из одного ответа модели не совпадут
    call_numbers = itertools.count(1)

    def get_advice(*, question: str, context: str | None = None, related_files: list[str] | None = None) -> str:
        """
        Запускает советника на вопросе и возвращает его ответ.

            question: вопрос.
            context: что спросивший уже знает и пробовал; None — не указан.
            related_files: пути файлов проекта по вопросу; None — не указаны.

        Возвращает: Ответ советника; длиннее ADVICE_LENGTH_LIMIT — начало ответа и путь к файлу.
            Ошибку для агента поднимает ToolException.
        """
        call_number = next(call_numbers)
        if call_number > ADVICE_CALL_LIMIT:
            raise ToolException(f"Ошибка: советника уже спрашивали {ADVICE_CALL_LIMIT} раз, больше нельзя.")

        private_dir_name = caller_context.caller_private_dir_name / f"{ADVISOR_ROLE.name}_{call_number}"
        related_paths = _copy_private_files(
            file_paths = related_files or [],
            project_dir = project_dir,
            target_dir = project_dir / PRIVATE_ROOT / private_dir_name / RELATED_DIR_NAME,
        )
        advice_dir = run_role(
            cfg = caller_context.cfg,
            role = ADVISOR_ROLE,
            journal_name = f"{caller_context.caller_journal_name}.{ADVISOR_ROLE.name}_{call_number}",
            task = ADVISOR_TASK.format(
                caller_name = caller_context.caller_name,
                question = question,
                context = context or "(не указан)",
                related_files = _show_files(file_paths = related_paths),
            ),
            input_dirs = (),
            private_dir_name = private_dir_name,
            extra_readable_dirs = (project_dir,),
            extra_writable_dirs = (project_dir / CHECK_DIR,),
        )
        advice_path = advice_dir / ADVICE_FILE_NAME
        if not advice_path.is_file():
            raise ToolException(
                f"Ошибка: советник не дал ответа. Его черновик: {advice_dir.relative_to(project_dir)}"
            )

        advice = advice_path.read_text(encoding = "utf-8", errors = "replace")
        if len(advice) <= ADVICE_LENGTH_LIMIT:
            return advice

        return (
            advice[:ADVICE_LENGTH_LIMIT]
            + f"\n\n(Ответ обрезан: всего знаков {len(advice)}. Полностью — в файле "
            f"{advice_path.relative_to(project_dir)})"
        )

    return StructuredTool.from_function(
        func = get_advice,
        name = GET_ADVICE_TOOL_NAME,
        description = GET_ADVICE_DESCRIPTION,
        args_schema = GetAdviceArguments,
        handle_tool_error = True,
    )


def _copy_private_files(*, file_paths: list[str], project_dir: Path, target_dir: Path) -> list[str]:
    """
    Копирует файлы из папки личных папок в папку советника: иначе они ему закрыты.

        file_paths: пути файлов от спросившего, относительно папки проекта.
        project_dir: папка проекта.
        target_dir: папка копий внутри личной папки советника.

    Возвращает: Пути для задачи советнику: файлы проекта — как есть, файлы из личных папок — пути копий.
    """
    shown_paths = []
    for index, file_path in enumerate(file_paths):
        source = (project_dir / file_path).resolve()
        if not source.is_relative_to(project_dir / PRIVATE_ROOT) or not source.is_file():
            shown_paths.append(file_path)
            continue

        copy_path = target_dir / f"{index}_{source.name}"
        copy_path.parent.mkdir(parents = True, exist_ok = True)
        shutil.copy2(source, copy_path)
        shown_paths.append(str(copy_path.relative_to(project_dir)))

    return shown_paths


def _show_files(*, file_paths: list[str]) -> str:
    """
    Показывает список файлов для задачи советнику.

        file_paths: пути файлов проекта.

    Возвращает: Пути по одному в строке; пометку, если файлов нет.
    """
    if not file_paths:
        return "(не указаны)"

    return "\n".join(f"- {path}" for path in file_paths)
