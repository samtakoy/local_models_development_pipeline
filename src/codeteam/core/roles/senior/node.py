"""Узел сеньора в графе пайплайна: план реализации текущего этапа."""

import shutil
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.architect import ARCHITECTURE_FILE_NAME
from codeteam.core.roles.common import STAGE_TASK_DIR_NAME, build_stage_dir_name, make_journal_name, run_role
from codeteam.core.roles.senior.config import SENIOR_ROLE
from codeteam.core.roles.senior.prompts import SENIOR_TASK


def senior_node(state: PipelineState, config: RunnableConfig):
    """Запускает сеньора текущего этапа: по общему решению и файлу этапа он пишет план реализации."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = state["stages"]
    stage_file = stages.current_file
    stage_dir_name = build_stage_dir_name(stage_file = stage_file)
    stage_task_dir = _prepare_stage_task_dir(
        plan_dir = state["plan_dir"],
        stage_file = stage_file,
        target_dir = project_dir / PRIVATE_ROOT / stage_dir_name / STAGE_TASK_DIR_NAME,
    )
    task = SENIOR_TASK.format(
        task = state["task"],
        stage_task_dir = stage_task_dir.relative_to(project_dir),
        architecture_file = ARCHITECTURE_FILE_NAME,
        stage_file = stage_file.name,
    )
    stage_plan_dir = run_role(
        cfg = cfg,
        role = SENIOR_ROLE,
        journal_name = make_journal_name(
            journal_count = state["journal_count"],
            label = f"{stage_dir_name}_{SENIOR_ROLE.name}",
        ),
        task = task,
        input_dirs = (stage_task_dir,),
        private_dir_name = stage_dir_name / SENIOR_ROLE.name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
    )

    return {"stages": replace(stages, plan_dir = stage_plan_dir), "journal_count": state["journal_count"] + 1}


def _prepare_stage_task_dir(*, plan_dir: Path, stage_file: Path, target_dir: Path) -> Path:
    """
    Копирует общее решение архитектора и файл этапа в папку задачи этапа.

        plan_dir: папка черновика архитектора.
        stage_file: файл этапа.
        target_dir: папка задачи этапа.

    Возвращает: Папку задачи этапа.
    """
    target_dir.mkdir(parents = True, exist_ok = True)
    shutil.copy2(plan_dir / ARCHITECTURE_FILE_NAME, target_dir / ARCHITECTURE_FILE_NAME)
    shutil.copy2(stage_file, target_dir / stage_file.name)

    return target_dir
