"""Узел приёмщика этапа в графе пайплайна: проверка этапа в запущенном приложении, вердикт и замечания."""

import logging
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.common.git import commit_all
from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Review
from codeteam.core.roles.common import STAGE_TASK_DIR_NAME, build_stage_dir_name, check_review_limit, \
    make_journal_name, next_review_round, parse_stage_number, read_stage_title, read_verdict, run_role
from codeteam.core.roles.developer import DEVELOPER_ROLE
from codeteam.core.roles.developer_review.config import DEVELOPER_REVIEW_ROLE
from codeteam.core.roles.developer_review.prompts import DEVELOPER_REVIEW_TASK

logger = logging.getLogger(__name__)


def developer_review_node(state: PipelineState, config: RunnableConfig):
    """
    Коммитит работу разработчика и запускает приёмщика этапа: он запускает тесты и приложение,
    проходит шаги проверки этапа и пишет вердикт с замечаниями.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_dir_name = build_stage_dir_name(stage_file = stages.current_file)
    review_round = next_review_round(review = state["review"], target = DEVELOPER_ROLE.name)

    message = (
        f"codeteam: этап {parse_stage_number(stage_file = stages.current_file)} — "
        f"{read_stage_title(stage_file = stages.current_file)}: код разработчика, приёмка круг {review_round}"
    )
    if commit_all(project_dir = project_dir, message = message):
        logger.info(f"[git] коммит: {message}")
    else:
        logger.info(f"[git] перед приёмкой круг {review_round} новых изменений нет, коммита нет")

    stage_task_dir = project_dir / PRIVATE_ROOT / stage_dir_name / STAGE_TASK_DIR_NAME
    remarks_dir = run_role(
        cfg = cfg,
        role = DEVELOPER_REVIEW_ROLE,
        journal_name = make_journal_name(
            journal_count = state["journal_count"],
            label = f"{stage_dir_name}_{DEVELOPER_REVIEW_ROLE.name}_{review_round}",
        ),
        task = DEVELOPER_REVIEW_TASK.format(
            task = state["task"],
            stage_task_dir = stage_task_dir.relative_to(project_dir),
            stage_plan_dir = stages.plan_dir.relative_to(project_dir),
        ),
        input_dirs = (stage_task_dir, stages.plan_dir),
        private_dir_name = stage_dir_name / DEVELOPER_REVIEW_ROLE.name / f"round_{review_round}",
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
    )
    review = Review(
        target = DEVELOPER_ROLE.name,
        remarks_dir = remarks_dir,
        round = review_round,
        accepted = read_verdict(remarks_dir = remarks_dir),
    )
    check_review_limit(review = review, mode = cfg.review.developer)

    return {"review": review, "journal_count": state["journal_count"] + 1}
