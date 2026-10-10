"""Узел разработчика в графе пайплайна: код текущего этапа."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import build_stage_dir_name, make_journal_name, rework_for, role_private_dir_name, \
    run_role
from codeteam.core.roles.developer.config import DEVELOPER_ROLE
from codeteam.core.roles.developer.prompts import DEVELOPER_FIX_TASK, DEVELOPER_TASK


def developer_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает разработчика текущего этапа: по плану сеньора он пишет код этапа в папке проекта.
    Если работу вернули на доработку — разработчик исправляет код по замечаниям.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_dir_name = build_stage_dir_name(stage_file = stages.current_file)
    stage_plan_dir = stages.plan_dir
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = stage_dir_name,
        role_name = DEVELOPER_ROLE.name,
        rework = state["rework"],
    )
    rework = rework_for(rework = state["rework"], role_name = DEVELOPER_ROLE.name)
    if rework is not None:
        task = DEVELOPER_FIX_TASK.format(
            stage_plan_dir = stage_plan_dir.relative_to(project_dir),
            remarks_dir = rework.remarks_dir.relative_to(project_dir),
        )
        input_dirs = (stage_plan_dir, rework.remarks_dir)
    else:
        task = DEVELOPER_TASK.format(stage_plan_dir = stage_plan_dir.relative_to(project_dir))
        input_dirs = (stage_plan_dir,)

    run_role(
        cfg = cfg,
        role = DEVELOPER_ROLE,
        journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name),
        task = task,
        input_dirs = input_dirs,
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
        extra_command_writable_dirs = (),
    )

    return {"rework": None, "journal_count": state["journal_count"] + 1}
