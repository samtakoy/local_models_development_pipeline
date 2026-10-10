"""Узел приёмщика этапа в графе пайплайна: проверка этапа в запущенном приложении, вердикт и замечания."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.common.git import list_uncommitted_changes
from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Review
from codeteam.core.roles.common import STAGE_TASK_DIR_NAME, build_stage_dir_name, clean_project_check, \
    make_journal_name, make_rework, next_review_round, read_verdict, role_private_dir_name, run_role, \
    tracked_changes_check
from codeteam.core.roles.developer import DEVELOPER_ROLE
from codeteam.core.roles.developer_review.config import DEVELOPER_REVIEW_ROLE
from codeteam.core.roles.developer_review.prompts import DEVELOPER_REVIEW_TASK, TRACKED_CHANGES_REMARK

logger = logging.getLogger(__name__)


def developer_review_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает приёмщика этапа на закоммиченном коде разработчика: он запускает тесты и приложение,
    проходит шаги проверки этапа и пишет вердикт с замечаниями.
    Правки проекта приёмщиком ловят проверки после шага и при сдаче; оставшиеся правки — предупреждение в лог.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_dir_name = build_stage_dir_name(stage_file = stages.current_file)
    review_round = next_review_round(review = state["review"], target = DEVELOPER_ROLE.name)
    stage_task_dir = project_dir / PRIVATE_ROOT / stage_dir_name / STAGE_TASK_DIR_NAME
    # проверки правок проекта знают папку проекта только при запуске, поэтому добавляются к описанию роли здесь
    guarded_role = replace(
        DEVELOPER_REVIEW_ROLE,
        step_checks = (*DEVELOPER_REVIEW_ROLE.step_checks, tracked_changes_check(
            project_dir = project_dir,
            remark = TRACKED_CHANGES_REMARK,
        )),
        answer_checks = (*DEVELOPER_REVIEW_ROLE.answer_checks, clean_project_check(project_dir = project_dir)),
    )
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = stage_dir_name,
        role_name = DEVELOPER_REVIEW_ROLE.name,
        rework = state["rework"],
    )
    remarks_dir = run_role(
        cfg = cfg,
        role = guarded_role,
        journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name),
        task = DEVELOPER_REVIEW_TASK.format(
            task = state["task"],
            stage_task_dir = stage_task_dir.relative_to(project_dir),
            stage_plan_dir = stages.plan_dir.relative_to(project_dir),
        ),
        input_dirs = (stage_task_dir, stages.plan_dir),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
        extra_command_writable_dirs = (),
    )
    left_changes = [path for _, path in list_uncommitted_changes(project_dir = project_dir)]
    if left_changes:
        logger.warning(f"[приёмка] приёмщик оставил правки в проекте: {', '.join(left_changes)}")

    review = Review(
        target = DEVELOPER_ROLE.name,
        round = review_round,
        accepted = read_verdict(remarks_dir = remarks_dir),
    )
    rework = make_rework(review = review, remarks_dir = remarks_dir, preserve_draft = True, preserve_context = True)

    return {"review": review, "rework": rework, "journal_count": state["journal_count"] + 1}
