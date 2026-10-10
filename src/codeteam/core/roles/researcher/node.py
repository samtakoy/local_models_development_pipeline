"""Узел исследователя в графе пайплайна: отчёт о текущем коде по задаче."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import make_journal_name, role_private_dir_name, run_role
from codeteam.core.roles.researcher.config import RESEARCHER_ROLE
from codeteam.core.roles.researcher.prompts import RESEARCHER_TASK


def researcher_node(state: PipelineState, config: RunnableConfig):
    """Запускает исследователя кода на задаче пользователя."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = RESEARCHER_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    research_dir = run_role(
        cfg = cfg,
        role = RESEARCHER_ROLE,
        journal_name = journal_name,
        task = RESEARCHER_TASK.format(task = state["task"]),
        input_dirs = (),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )

    return {"research_dir": research_dir, "rework": None, "journal_name": journal_name, "journal_count": state["journal_count"] + 1}
