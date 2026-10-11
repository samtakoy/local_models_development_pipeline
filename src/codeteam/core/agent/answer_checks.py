"""Проверки сдачи работы: по черновику и проекту решают, принять ли ответ агента."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codeteam.core.agent.prompts import MISSING_ANSWER_FILES_REMARK


@dataclass(frozen = True)
class AnswerContext:
    """
    Сдача работы агентом: что нужно проверкам сдачи.

        project_dir: папка проекта.
        draft_dir: папка черновика агента.
    """

    project_dir: Path
    draft_dir: Path


# Проверка сдачи: сдача работы → замечание агенту или None, если ответ годится.
AnswerCheck = Callable[[AnswerContext], str | None]


def required_files_check(*, file_names: tuple[str, ...]) -> AnswerCheck:
    """
    Собирает проверку сдачи: в черновике есть все обязательные файлы.

        file_names: имена обязательных файлов черновика.

    Возвращает: Проверку сдачи.
    """
    def check(context: AnswerContext) -> str | None:
        """Находит обязательные файлы, которых нет в черновике."""
        missing_names = [name for name in file_names if not (context.draft_dir / name).is_file()]
        if not missing_names:
            return None

        return MISSING_ANSWER_FILES_REMARK.format(file_names = ", ".join(missing_names))

    return check
