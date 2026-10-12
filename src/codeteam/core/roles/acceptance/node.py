"""Узел итоговой приёмки в графе пайплайна: итоговый вердикт по отчётам тестировщиков и этап исправлений
по плану доработки."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.acceptance.checks import FIX_PLAN_FILE_NAME
from codeteam.core.roles.acceptance.config import ACCEPTANCE_ROLE
from codeteam.core.roles.acceptance.prompts import ACCEPTANCE_TASK, FIX_STAGE_TEXT, REPORT_DIR_LINE
from codeteam.core.roles.common import PipelineError, make_journal_name, parse_stage_number, read_verdict, \
    role_private_dir_name, run_role
from codeteam.core.roles.senior import SENIOR_ROLE

logger = logging.getLogger(__name__)

# Наибольшее число этапов исправлений по итогам приёмки за прогон.
FIX_ROUND_LIMIT = 2


def acceptance_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает итоговую приёмку по отчётам тестировщиков. Отчётов нет — приёмка пропускается.
    Приёмка видит задачу, чеклист требований и отчёты, проект ей закрыт. Вердикт FIX, круги исправлений
    не кончились и в ролях пайплайна есть роли этапа — в конец этапов добавляется этап исправлений по плану
    доработки, после него тестировщики и приёмка повторяются.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния: папка вердикта и плана, а если добавлен этап исправлений — этапы;
        пустое, если отчётов тестировщиков нет.
    """
    report_dirs = tuple(
        folder
        for folder in (state["tester_dir"], state["web_tester_dir"], state["web_scenarios_tester_dir"])
        if folder is not None
    )
    if not report_dirs:
        logger.info(f"[{ACCEPTANCE_ROLE.name}] отчётов тестировщиков нет, приёмка пропущена")
        return {}

    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = ACCEPTANCE_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    verdict_dir = run_role(
        cfg = cfg,
        role = ACCEPTANCE_ROLE,
        journal_name = journal_name,
        task = ACCEPTANCE_TASK.format(
            task = state["task"],
            requirements_file = state["requirements_file"].relative_to(project_dir),
            report_dirs = "\n".join(
                REPORT_DIR_LINE.format(path = folder.relative_to(project_dir)) for folder in report_dirs
            ),
        ),
        input_dirs = (state["requirements_dir"], *report_dirs),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )
    update = {
        "acceptance_dir": verdict_dir,
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }
    if read_verdict(remarks_dir = verdict_dir):
        logger.info(f"[{ACCEPTANCE_ROLE.name}] задача принята: {verdict_dir}")
        return update

    stages = state["stages"]
    if SENIOR_ROLE.name not in cfg.roles or stages is None:
        logger.warning(f"[{ACCEPTANCE_ROLE.name}] задача не принята, ролей этапа нет — план доработки: {verdict_dir}")
        return update

    if stages.fix_rounds >= FIX_ROUND_LIMIT:
        logger.warning(
            f"[{ACCEPTANCE_ROLE.name}] задача не принята, круги исправлений ({FIX_ROUND_LIMIT}) кончились, "
            f"план доработки: {verdict_dir}"
        )
        return update

    fix_round = stages.fix_rounds + 1
    fix_stage_file = _write_fix_stage(
        plan_file = verdict_dir / FIX_PLAN_FILE_NAME,
        stage_number = _next_stage_number(stage_files = stages.files),
        target_dir = project_dir / PRIVATE_ROOT / private_dir_name,
        fix_round = fix_round,
    )
    logger.info(f"[{ACCEPTANCE_ROLE.name}] задача не принята, добавлен этап исправлений {fix_stage_file.name}")

    return {
        **update,
        "stages": replace(stages, files = (*stages.files, fix_stage_file), fix_rounds = fix_round),
    }


def _next_stage_number(*, stage_files: tuple[Path, ...]) -> str:
    """
    Находит номер следующего этапа: наибольший номер среди этапов плюс один.

        stage_files: файлы этапов.

    Возвращает: Номер с тем же числом цифр, что у наибольшего, например 006 после 005.
    """
    largest = max((parse_stage_number(stage_file = stage_file) for stage_file in stage_files), key = int)

    return str(int(largest) + 1).zfill(len(largest))


def _write_fix_stage(*, plan_file: Path, stage_number: str, target_dir: Path, fix_round: int) -> Path:
    """
    Пишет файл этапа исправлений: план доработки внутри описания этапа.

        plan_file: файл плана доработки итоговой приёмки.
        stage_number: номер этапа исправлений.
        target_dir: папка, куда положить файл этапа.
        fix_round: номер круга исправлений.

    Возвращает: Файл этапа исправлений <номер>_fix_<круг>.md. Ошибку поднимает PipelineError, если плана нет.
    """
    if not plan_file.is_file():
        raise PipelineError(f"вердикт итоговой приёмки FIX, а плана доработки {plan_file} нет")

    fix_stage_file = target_dir / f"{stage_number}_fix_{fix_round}.md"
    plan = plan_file.read_text(encoding = "utf-8", errors = "replace").strip()
    fix_stage_file.write_text(FIX_STAGE_TEXT.format(round = fix_round, plan = plan), encoding = "utf-8")

    return fix_stage_file
