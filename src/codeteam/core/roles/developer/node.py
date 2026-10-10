"""Узел разработчика в графе пайплайна: код текущего этапа."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import build_stage_dir_name, make_journal_name, needs_fix, run_role
from codeteam.core.roles.developer.config import DEVELOPER_ROLE
from codeteam.core.roles.developer.prompts import DEVELOPER_FIX_TASK, DEVELOPER_TASK


def developer_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает разработчика текущего этапа: по плану сеньора он пишет код этапа в папке проекта.
    Если приёмщик вернул этап на доработку — разработчик исправляет код по замечаниям.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_dir_name = build_stage_dir_name(stage_file = stages.current_file)
    stage_plan_dir = stages.plan_dir
    review = state["review"]
    if needs_fix(review = review, target = DEVELOPER_ROLE.name):
        task = DEVELOPER_FIX_TASK.format(
            stage_plan_dir = stage_plan_dir.relative_to(project_dir),
            remarks_dir = review.remarks_dir.relative_to(project_dir),
        )
        input_dirs = (stage_plan_dir, review.remarks_dir)
        label = f"{stage_dir_name}_{DEVELOPER_ROLE.name}_fix_{review.round}"
    else:
        task = DEVELOPER_TASK.format(stage_plan_dir = stage_plan_dir.relative_to(project_dir))
        input_dirs = (stage_plan_dir,)
        label = f"{stage_dir_name}_{DEVELOPER_ROLE.name}"

    run_role(
        cfg = cfg,
        role = DEVELOPER_ROLE,
        journal_name = make_journal_name(journal_count = state["journal_count"], label = label),
        task = task,
        input_dirs = input_dirs,
        private_dir_name = stage_dir_name / DEVELOPER_ROLE.name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
        extra_command_writable_dirs = (),
    )

    return {"journal_count": state["journal_count"] + 1}
