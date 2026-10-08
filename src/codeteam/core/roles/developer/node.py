"""Узел разработчика в графе пайплайна: код текущего этапа."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import build_stage_dir_name, make_journal_name, run_role
from codeteam.core.roles.developer.config import DEVELOPER_ROLE
from codeteam.core.roles.developer.prompts import DEVELOPER_TASK


def developer_node(state: PipelineState, config: RunnableConfig):
    """Запускает разработчика текущего этапа: по плану сеньора он пишет код этапа в папке проекта."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_dir_name = build_stage_dir_name(stage_file = stages.current_file)
    stage_plan_dir = stages.plan_dir
    run_role(
        cfg = cfg,
        role = DEVELOPER_ROLE,
        journal_name = make_journal_name(
            journal_count = state["journal_count"],
            label = f"{stage_dir_name}_{DEVELOPER_ROLE.name}",
        ),
        task = DEVELOPER_TASK.format(stage_plan_dir = stage_plan_dir.relative_to(project_dir)),
        input_dirs = (stage_plan_dir,),
        private_dir_name = stage_dir_name / DEVELOPER_ROLE.name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
    )

    return {"journal_count": state["journal_count"] + 1}
