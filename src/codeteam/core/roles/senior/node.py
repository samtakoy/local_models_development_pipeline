"""Узел сеньора в графе пайплайна: план реализации текущего этапа."""

import shutil
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import STAGE_TASK_DIR_NAME, build_stage_dir_name, make_journal_name, \
    role_private_dir_name, run_role
from codeteam.core.roles.senior.config import SENIOR_ROLE
from codeteam.core.roles.senior.prompts import SENIOR_TASK


def senior_node(state: PipelineState, config: RunnableConfig):
    """
    Начинает следующий этап и запускает сеньора: по общему решению и файлу этапа он пишет план реализации.
    Счёт кругов ревью прошлого этапа сбрасывается.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stages = replace(state["stages"], started = state["stages"].started + 1, plan_dir = None)
    stage_file = stages.current_file
    stage_dir_name = build_stage_dir_name(stage_file = stage_file)
    architecture_file = state["architecture_file"]
    stage_task_dir = _prepare_stage_task_dir(
        architecture_file = architecture_file,
        stage_file = stage_file,
        target_dir = project_dir / PRIVATE_ROOT / stage_dir_name / STAGE_TASK_DIR_NAME,
    )
    task = SENIOR_TASK.format(
        task = state["task"],
        stage_task_dir = stage_task_dir.relative_to(project_dir),
        architecture_file = architecture_file.name,
        stage_file = stage_file.name,
    )
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = stage_dir_name,
        role_name = SENIOR_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    stage_plan_dir = run_role(
        cfg = cfg,
        role = SENIOR_ROLE,
        journal_name = journal_name,
        task = task,
        input_dirs = (stage_task_dir,),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )

    return {
        "stages": replace(stages, plan_dir = stage_plan_dir),
        "review": None,
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }


def _prepare_stage_task_dir(*, architecture_file: Path, stage_file: Path, target_dir: Path) -> Path:
    """
    Копирует общее решение архитектора и файл этапа в папку задачи этапа.

        architecture_file: файл общего решения архитектора.
        stage_file: файл этапа.
        target_dir: папка задачи этапа.

    Возвращает: Папку задачи этапа.
    """
    target_dir.mkdir(parents = True, exist_ok = True)
    shutil.copy2(architecture_file, target_dir / architecture_file.name)
    shutil.copy2(stage_file, target_dir / stage_file.name)

    return target_dir
