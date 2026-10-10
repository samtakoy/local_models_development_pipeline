"""Узел менеджера продукта в графе пайплайна: чеклист требований."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import PipelineError, make_journal_name, role_private_dir_name, run_role
from codeteam.core.roles.pm.config import PM_ROLE, REQUIREMENTS_FILE_NAME
from codeteam.core.roles.pm.prompts import PM_TASK


def pm_node(state: PipelineState, config: RunnableConfig):
    """Запускает менеджера продукта: по тексту задачи пользователя он пишет чеклист требований без доступа к проекту."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    private_dir_name = role_private_dir_name(
        project_dir = Path(cfg.project_path).resolve(),
        parent = Path("."),
        role_name = PM_ROLE.name,
        rework = state["rework"],
    )
    requirements_dir = run_role(
        cfg = cfg,
        role = PM_ROLE,
        journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name),
        task = PM_TASK.format(task = state["task"]),
        input_dirs = (),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )
    if not (requirements_dir / REQUIREMENTS_FILE_NAME).is_file():
        raise PipelineError(f"в черновике менеджера продукта {requirements_dir} нет файла {REQUIREMENTS_FILE_NAME}")

    return {"requirements_dir": requirements_dir, "rework": None, "journal_count": state["journal_count"] + 1}
