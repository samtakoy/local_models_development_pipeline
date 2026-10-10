"""Запуск пайплайна агентов на задаче проекта."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.core.pipeline.graph import create_pipeline_graph
from codeteam.core.pipeline.project import ProjectSettings
from codeteam.core.pipeline.project_setup import prepare_project
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState


def run_pipeline(*, project: ProjectSettings, run_dir: Path, model_name: str, settings: Settings) -> PipelineState:
    """
    Готовит папку проекта, запускает пайплайн агентов на задаче проекта и ждёт окончания.

        project: проект и задача пользователя.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        settings: настройки приложения.

    Возвращает: Итоговое состояние пайплайна: папки результатов агентов.
    """
    prepare_project(project_dir = Path(project.path).resolve(), run_name = run_dir.name)

    config = RunnableConfig(
        configurable = {
            PIPELINE_CFG_NAME: PipelineConfig(
                project_path = project.path,
                run_dir = run_dir,
                model_name = model_name,
                review = project.review,
                settings = settings,
            )
        }
    )
    initial_state = PipelineState(
        task = project.task,
        requirements_dir = None,
        research_dir = None,
        plan_dir = None,
        stages = None,
        review = None,
        rework = None,
        journal_count = 0,
    )

    return create_pipeline_graph(review = project.review).invoke(input = initial_state, config = config)
