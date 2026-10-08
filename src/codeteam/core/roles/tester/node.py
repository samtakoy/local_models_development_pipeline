"""Узел тестировщика в графе пайплайна: проверка готового приложения в браузере, вердикт и отчёт."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.common.git import list_uncommitted_changes
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import clean_project_check, make_journal_name, read_verdict, run_role, \
    tracked_changes_check
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME
from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.tester.prompts import TESTER_TASK

logger = logging.getLogger(__name__)


def tester_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает тестировщика после последнего этапа: он запускает приложение, проходит требования заказчика
    в браузере и пишет вердикт с отчётом. На доработку не возвращает: вердикт и отчёт — итог прогона.
    Правки проекта тестировщиком ловят проверки после шага и при сдаче; оставшиеся правки — предупреждение в лог.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    # проверки правок проекта знают папку проекта только при запуске, поэтому добавляются к описанию роли здесь
    guarded_role = replace(
        TESTER_ROLE,
        step_checks = (*TESTER_ROLE.step_checks, tracked_changes_check(project_dir = project_dir)),
        answer_checks = (*TESTER_ROLE.answer_checks, clean_project_check(project_dir = project_dir)),
    )
    report_dir = run_role(
        cfg = cfg,
        role = guarded_role,
        journal_name = make_journal_name(journal_count = state["journal_count"], label = TESTER_ROLE.name),
        task = TESTER_TASK.format(
            task = state["task"],
            requirements_file = (requirements_dir / REQUIREMENTS_FILE_NAME).relative_to(project_dir),
        ),
        input_dirs = (requirements_dir,),
        private_dir_name = Path(TESTER_ROLE.name),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
    )
    left_changes = [path for _, path in list_uncommitted_changes(project_dir = project_dir)]
    if left_changes:
        logger.warning(f"[тестировщик] оставил правки в проекте: {', '.join(left_changes)}")

    verdict = "принято" if read_verdict(remarks_dir = report_dir) else "не принято"
    logger.info(f"[тестировщик] приложение {verdict}, отчёт: {report_dir}")

    return {"journal_count": state["journal_count"] + 1}
