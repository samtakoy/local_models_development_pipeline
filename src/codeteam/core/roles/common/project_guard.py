"""Охрана проекта от правок роли, которая только проверяет: откат изменённых файлов проекта и замечания."""

from pathlib import Path

from codeteam.common.git import UNTRACKED_STATUS, list_uncommitted_changes, restore_paths
from codeteam.core.agent.answer_checks import AnswerContext
from codeteam.core.agent.step_hooks import StepCheck
from codeteam.core.roles.common.prompts import PROJECT_CHANGES_REMARK


def tracked_changes_check(*, project_dir: Path, remark: str) -> StepCheck:
    """
    Собирает проверку после шага: роль изменила отслеживаемые файлы проекта. Изменённые файлы
    возвращаются к последнему коммиту, замечание называет их.

    Проект на начало работы роли должен быть закоммичен.

        project_dir: папка проекта.
        remark: текст замечания роли с заготовкой {paths} - изменённые файлы через запятую.

    Возвращает: Проверку после шага.
    """

    def check() -> str | None:
        """Возвращает к коммиту изменённые отслеживаемые файлы проекта."""
        changed_paths = tuple(sorted(
            path for status, path in list_uncommitted_changes(project_dir = project_dir) if status != UNTRACKED_STATUS
        ))
        if not changed_paths:
            return None

        restore_paths(project_dir = project_dir, paths = changed_paths)

        return remark.format(paths = ", ".join(changed_paths))

    return check


def clean_project_check(context: AnswerContext) -> str | None:
    """
    Проверка сдачи: в проекте нет незакоммиченных правок и новых файлов; папку черновика не смотрит.

    Проект на начало работы роли должен быть закоммичен.

        context: сдача работы агентом.

    Возвращает: Замечание со списком правок или None, если проект чистый.
    """
    changed_paths = [path for _, path in list_uncommitted_changes(project_dir = context.project_dir)]
    if not changed_paths:
        return None

    return PROJECT_CHANGES_REMARK.format(paths = ", ".join(changed_paths))
