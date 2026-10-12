"""Узел тестировщика в графе пайплайна: финальная проверка готового приложения."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import make_journal_name, role_private_dir_name, run_role
from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.tester.prompts import TESTER_TASK


def tester_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает тестировщика после последнего этапа: он проверяет требования заказчика в готовом приложении
    и пишет вердикт с отчётом.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния пайплайна: папка вердикта и отчёта в поле tester_dir.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = TESTER_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    report_dir = run_role(
        cfg = cfg,
        role = TESTER_ROLE,
        journal_name = journal_name,
        task = TESTER_TASK.format(
            task = state["task"],
            requirements_file = state["requirements_file"].relative_to(project_dir),
        ),
        input_dirs = (state["requirements_dir"],),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir / CHECK_DIR,),
        extra_command_writable_dirs = (project_dir,),
    )

    return {
        "tester_dir": report_dir,
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }
