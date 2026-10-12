"""Узел проверки по сценариям в графе пайплайна: прогон сценариев в браузере и вердикт оценщика."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import PipelineError, make_journal_name, role_private_dir_name, run_role
from codeteam.core.roles.web_scenarios import LaunchFileError, read_app_launch, scenario_files
from codeteam.core.roles.web_scenarios_tester.config import WEB_SCENARIOS_TESTER_ROLE
from codeteam.core.roles.web_scenarios_tester.prompts import WEB_SCENARIOS_TESTER_TASK
from codeteam.core.roles.web_scenarios_tester.runner import run_scenarios


def web_scenarios_tester_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Прогоняет сценарии составителя в браузере: запускает приложение, отдаёт каждый сценарий отдельному
    помощнику с браузером, затем оценщик без доступа к проекту сравнивает наблюдения со сценариями
    и пишет вердикт с отчётом. Ошибку поднимает PipelineError, если сценариев нет или файл запуска не читается.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния пайплайна: папка вердикта и отчёта в поле web_scenarios_tester_dir.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    scenarios_dir = state["web_scenarios_dir"]
    if scenarios_dir is None:
        raise PipelineError("сценариев проверки в браузере нет: роль web_scenarios должна работать раньше")

    try:
        launch = read_app_launch(draft_dir = scenarios_dir)
    except LaunchFileError as error:
        raise PipelineError(f"файл запуска в {scenarios_dir} не читается: {error}") from error

    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = WEB_SCENARIOS_TESTER_ROLE.name,
        rework = state["rework"],
    )
    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    observations_dir = run_scenarios(
        cfg = cfg,
        caller_name = WEB_SCENARIOS_TESTER_ROLE.name,
        private_dir_name = private_dir_name,
        journal_name = journal_name,
        launch = launch,
        scenario_paths = scenario_files(draft_dir = scenarios_dir),
    )
    report_dir = run_role(
        cfg = cfg,
        role = WEB_SCENARIOS_TESTER_ROLE,
        journal_name = journal_name,
        task = WEB_SCENARIOS_TESTER_TASK.format(
            task = state["task"],
            requirements_file = state["requirements_file"].relative_to(project_dir),
            scenarios_dir = scenarios_dir.relative_to(project_dir),
            observations_dir = observations_dir.relative_to(project_dir),
        ),
        input_dirs = (state["requirements_dir"], scenarios_dir, observations_dir),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )

    return {
        "web_scenarios_tester_dir": report_dir,
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }
