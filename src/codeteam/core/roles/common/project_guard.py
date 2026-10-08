"""Охрана проекта от правок роли, которая только проверяет: замечания, если она изменила файлы проекта."""

from pathlib import Path

from codeteam.common.git import UNTRACKED_STATUS, list_uncommitted_changes
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.step_hooks import StepCheck

# Замечание после шага: роль изменила отслеживаемые файлы проекта.
TRACKED_CHANGES_REMARK = (
    "Ты изменил файлы проекта: {paths}. Ты не можешь менять код проекта. "
    "Верни файлы как было: git checkout -- <файл>."
)

# Замечание при сдаче: проект не вернулся в состояние на начало работы роли.
PROJECT_CHANGES_REMARK = (
    "Проект изменён с начала твоей работы: {paths}. Перед сдачей верни проект как было: "
    "изменённые файлы — git checkout -- <файл>, новые файлы, которые создали ты или приложение, удали."
)


def tracked_changes_check(*, project_dir: Path) -> StepCheck:
    """
    Собирает проверку после шага: роль изменила отслеживаемые файлы проекта.

    Проект на начало работы роли должен быть закоммичен. О каждом изменённом файле замечание пишется
    один раз, пока файл не вернётся к закоммиченному состоянию.

        project_dir: папка проекта.

    Возвращает: Проверку после шага.
    """
    reported_paths: set[str] = set()

    def check() -> str | None:
        """Находит отслеживаемые файлы, изменённые после последнего замечания."""
        changed_paths = {
            path for status, path in list_uncommitted_changes(project_dir = project_dir) if status != UNTRACKED_STATUS
        }
        new_paths = sorted(changed_paths - reported_paths)
        reported_paths.clear()
        reported_paths.update(changed_paths)
        if not new_paths:
            return None

        return TRACKED_CHANGES_REMARK.format(paths = ", ".join(new_paths))

    return check


def clean_project_check(*, project_dir: Path) -> AnswerCheck:
    """
    Собирает проверку сдачи: в проекте нет незакоммиченных правок и новых файлов.

    Проект на начало работы роли должен быть закоммичен.

        project_dir: папка проекта.

    Возвращает: Проверку сдачи.
    """
    def check(answer_dir: Path) -> str | None:
        """Находит правки и новые файлы проекта; папку черновика не смотрит."""
        changed_paths = [path for _, path in list_uncommitted_changes(project_dir = project_dir)]
        if not changed_paths:
            return None

        return PROJECT_CHANGES_REMARK.format(paths = ", ".join(changed_paths))

    return check
