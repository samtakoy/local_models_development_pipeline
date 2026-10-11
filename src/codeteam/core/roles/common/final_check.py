"""Хелпер для узлов - тестировщиков (похожая логика).
Финальная проверка готового приложения: запуск проверяющей роли, её вердикт и этап исправлений по её отчёту."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.common.git import list_uncommitted_changes
from codeteam.core.agent.workspace import CHECK_DIR, PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common.private_dirs import role_private_dir_name
from codeteam.core.roles.common.project_guard import tracked_changes_check
from codeteam.core.roles.common.prompts import FIX_STAGE_TEXT
from codeteam.core.roles.common.review import read_verdict
from codeteam.core.roles.common.role_settings import RoleSettings
from codeteam.core.roles.common.run_role import make_journal_name, run_role

logger = logging.getLogger(__name__)

# Наибольшее число этапов исправлений по отчёту финальной проверки за прогон.
FIX_ROUND_LIMIT = 2

# Номер этапа исправлений: FIX_STAGE_NUMBER_BASE + номер круга, файл <номер>_fix_<круг>.md.
FIX_STAGE_NUMBER_BASE = 900

# Файл отчёта по требованиям в черновике проверяющей роли.
REPORT_FILE_NAME = "100_report.md"

# Файл в папке прогона: вердикт и отчёт последней финальной проверки.
TESTER_REPORT_FILE_NAME = "tester_report.md"


def run_final_check(
    *,
    state: PipelineState,
    config: RunnableConfig,
    role: RoleSettings,
    task_template: str,
    tracked_changes_remark: str,
) -> dict:
    """
    Запускает проверяющую роль после последнего этапа: она проверяет готовое приложение по требованиям
    заказчика и пишет вердикт с отчётом. Если приложение не принято и круги исправлений не кончились,
    добавляет в конец этапов этап исправлений с отчётом — его делает команда, после чего проверка повторяется.
    Правки проекта проверяющей ролью ловят проверки после шага и при сдаче; оставшиеся правки — предупреждение в лог.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.
        role: описание проверяющей роли.
        task_template: задача роли с полями {task} - задача заказчика и {requirements_file} - файл чеклиста.
        tracked_changes_remark: замечание роли после шага, изменившего файлы проекта; поле {paths} - файлы.

    Возвращает: Обновление состояния: папка проверки, а если добавлен этап исправлений — этапы.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    stages = state["stages"]
    test_round = stages.fix_rounds + 1
    # проверки правок проекта знают папку проекта только при запуске, поэтому добавляются к описанию роли здесь
    guarded_role = replace(
        role,
        step_checks = (*role.step_checks, tracked_changes_check(
            project_dir = project_dir,
            remark = tracked_changes_remark,
        )),
    )
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = role.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    report_dir = run_role(
        cfg = cfg,
        role = guarded_role,
        journal_name = journal_name,
        task = task_template.format(
            task = state["task"],
            requirements_file = state["requirements_file"].relative_to(project_dir),
        ),
        input_dirs = (requirements_dir,),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir / CHECK_DIR,),
        extra_command_writable_dirs = (project_dir,),
    )
    left_changes = [path for _, path in list_uncommitted_changes(project_dir = project_dir)]
    if left_changes:
        logger.warning(f"[{role.name}] оставил правки в проекте: {', '.join(left_changes)}")

    update = {
        "rework": None,
        "web_test_dir": report_dir,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }
    if read_verdict(remarks_dir = report_dir):
        logger.info(f"[{role.name}] приложение принято, отчёт: {report_dir}")
        return update

    if stages.fix_rounds >= FIX_ROUND_LIMIT:
        logger.warning(
            f"[{role.name}] приложение не принято, круги исправлений ({FIX_ROUND_LIMIT}) кончились, "
            f"отчёт: {report_dir}"
        )
        return update

    fix_stage_file = _write_fix_stage(
        report_dir = report_dir,
        target_dir = project_dir / PRIVATE_ROOT / private_dir_name,
        test_round = test_round,
    )
    logger.info(f"[{role.name}] приложение не принято, добавлен этап исправлений {fix_stage_file.name}")

    return {
        **update,
        "stages": replace(stages, files = (*stages.files, fix_stage_file), fix_rounds = test_round),
    }


def _write_fix_stage(*, report_dir: Path, target_dir: Path, test_round: int) -> Path:
    """
    Пишет файл этапа исправлений: отчёт проверяющей роли внутри описания этапа.

        report_dir: папка черновика проверяющей роли: вердикт и отчёт.
        target_dir: папка, куда положить файл этапа.
        test_round: номер круга проверки.

    Возвращает: Файл этапа исправлений <номер>_fix_<круг>.md.
    """
    fix_stage_file = target_dir / f"{FIX_STAGE_NUMBER_BASE + test_round}_fix_{test_round}.md"
    fix_stage_file.write_text(
        FIX_STAGE_TEXT.format(round = test_round, report = _read_report(report_dir = report_dir)),
        encoding = "utf-8",
    )

    return fix_stage_file


def write_tester_report(*, run_dir: Path, report_dir: Path) -> Path:
    """
    Пишет в папку прогона вердикт и отчёт последней финальной проверки одним файлом.

        run_dir: папка прогона.
        report_dir: папка черновика проверяющей роли: вердикт и отчёт.

    Возвращает: Файл tester_report.md в папке прогона.
    """
    report_file = run_dir / TESTER_REPORT_FILE_NAME
    report_file.write_text(_read_report(report_dir = report_dir) + "\n", encoding = "utf-8")

    return report_file


def _read_report(*, report_dir: Path) -> str:
    """
    Склеивает файлы *.md черновика проверяющей роли по порядку имён.

        report_dir: папка черновика проверяющей роли: вердикт и отчёт.

    Возвращает: Текст файлов через пустую строку.
    """
    return "\n\n".join(
        path.read_text(encoding = "utf-8", errors = "replace").strip() for path in sorted(report_dir.glob("*.md"))
    )
