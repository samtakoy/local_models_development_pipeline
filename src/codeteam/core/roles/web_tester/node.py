"""Узел веб-тестировщика в графе пайплайна: проверка готового приложения в браузере и этап исправлений по отчёту."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.common.git import list_uncommitted_changes
from codeteam.core.agent.workspace import CHECK_DIR, PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import clean_project_check, make_journal_name, read_verdict, role_private_dir_name, \
    run_role, tracked_changes_check
from codeteam.core.roles.web_tester.config import WEB_TESTER_ROLE
from codeteam.core.roles.web_tester.prompts import FIX_STAGE_TEXT, TRACKED_CHANGES_REMARK, WEB_TESTER_TASK

logger = logging.getLogger(__name__)

# Наибольшее число этапов исправлений по отчёту веб-тестировщика за прогон.
FIX_ROUND_LIMIT = 1

# Номер этапа исправлений: FIX_STAGE_NUMBER_BASE + номер круга, файл <номер>_fix_<круг>.md.
FIX_STAGE_NUMBER_BASE = 900


def web_tester_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает веб-тестировщика после последнего этапа: он запускает приложение, проходит требования заказчика
    в браузере и пишет вердикт с отчётом. Если приложение не принято и круги исправлений не кончились,
    добавляет в конец этапов этап исправлений с отчётом — его делает команда, после чего проверка повторяется.
    Правки проекта веб-тестировщиком ловят проверки после шага и при сдаче; оставшиеся правки — предупреждение в лог.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    stages = state["stages"]
    test_round = stages.fix_rounds + 1
    # проверки правок проекта знают папку проекта только при запуске, поэтому добавляются к описанию роли здесь
    guarded_role = replace(
        WEB_TESTER_ROLE,
        step_checks = (*WEB_TESTER_ROLE.step_checks, tracked_changes_check(
            project_dir = project_dir,
            remark = TRACKED_CHANGES_REMARK,
        )),
        answer_checks = (*WEB_TESTER_ROLE.answer_checks, clean_project_check(project_dir = project_dir)),
    )
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = WEB_TESTER_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    report_dir = run_role(
        cfg = cfg,
        role = guarded_role,
        journal_name = journal_name,
        task = WEB_TESTER_TASK.format(
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
        logger.warning(f"[веб-тестировщик] оставил правки в проекте: {', '.join(left_changes)}")

    update = {"rework": None, "journal_name": journal_name, "journal_count": state["journal_count"] + 1}
    if read_verdict(remarks_dir = report_dir):
        logger.info(f"[веб-тестировщик] приложение принято, отчёт: {report_dir}")
        return update

    if stages.fix_rounds >= FIX_ROUND_LIMIT:
        logger.warning(
            f"[веб-тестировщик] приложение не принято, круги исправлений ({FIX_ROUND_LIMIT}) кончились, "
            f"отчёт: {report_dir}"
        )
        return update

    fix_stage_file = _write_fix_stage(
        report_dir = report_dir,
        target_dir = project_dir / PRIVATE_ROOT / private_dir_name,
        test_round = test_round,
    )
    logger.info(f"[веб-тестировщик] приложение не принято, добавлен этап исправлений {fix_stage_file.name}")

    return {
        **update,
        "stages": replace(stages, files = (*stages.files, fix_stage_file), fix_rounds = test_round),
    }


def _write_fix_stage(*, report_dir: Path, target_dir: Path, test_round: int) -> Path:
    """
    Пишет файл этапа исправлений: отчёт веб-тестировщика внутри описания этапа.

        report_dir: папка черновика веб-тестировщика: вердикт и отчёт.
        target_dir: папка, куда положить файл этапа.
        test_round: номер круга проверки.

    Возвращает: Файл этапа исправлений <номер>_fix_<круг>.md.
    """
    report = "\n\n".join(
        path.read_text(encoding = "utf-8", errors = "replace").strip() for path in sorted(report_dir.glob("*.md"))
    )
    fix_stage_file = target_dir / f"{FIX_STAGE_NUMBER_BASE + test_round}_fix_{test_round}.md"
    fix_stage_file.write_text(FIX_STAGE_TEXT.format(round = test_round, report = report), encoding = "utf-8")

    return fix_stage_file
