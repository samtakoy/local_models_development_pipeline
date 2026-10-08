"""Проверки сдачи работы: по папке черновика решают, принять ли ответ агента."""

from collections.abc import Callable
from pathlib import Path

from codeteam.core.agent.prompts import MISSING_ANSWER_FILES_REMARK

# Проверка сдачи: папка черновика агента → замечание агенту или None, если ответ годится.
AnswerCheck = Callable[[Path], str | None]


def required_files_check(*, file_names: tuple[str, ...]) -> AnswerCheck:
    """
    Собирает проверку сдачи: в черновике есть все обязательные файлы.

        file_names: имена обязательных файлов черновика.

    Возвращает: Проверку сдачи.
    """
    def check(answer_dir: Path) -> str | None:
        """Находит обязательные файлы, которых нет в черновике."""
        missing_names = [name for name in file_names if not (answer_dir / name).is_file()]
        if not missing_names:
            return None

        return MISSING_ANSWER_FILES_REMARK.format(file_names = ", ".join(missing_names))

    return check
