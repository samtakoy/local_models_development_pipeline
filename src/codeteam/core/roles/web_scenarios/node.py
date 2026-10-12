"""Узел составителя сценариев в графе пайплайна: сценарии проверки готового приложения в браузере."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import make_journal_name, role_private_dir_name, run_role
from codeteam.core.roles.web_scenarios.config import WEB_SCENARIOS_ROLE
from codeteam.core.roles.web_scenarios.prompts import WEB_SCENARIOS_TASK


def web_scenarios_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает составителя сценариев после последнего этапа: он читает задачу, чеклист и код проекта
    и пишет файл запуска приложения и сценарии проверки в браузере.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния пайплайна: папка файла запуска и сценариев в поле web_scenarios_dir.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = WEB_SCENARIOS_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    scenarios_dir = run_role(
        cfg = cfg,
        role = WEB_SCENARIOS_ROLE,
        journal_name = journal_name,
        task = WEB_SCENARIOS_TASK.format(
            task = state["task"],
            requirements_file = state["requirements_file"].relative_to(project_dir),
        ),
        input_dirs = (state["requirements_dir"],),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )

    return {
        "web_scenarios_dir": scenarios_dir,
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }
