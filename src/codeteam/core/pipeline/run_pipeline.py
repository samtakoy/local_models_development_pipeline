"""Запуск пайплайна агентов на задаче проекта."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.core.pipeline.graph import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, create_pipeline_graph
from codeteam.core.pipeline.project import ProjectSettings


def run_pipeline(*, project: ProjectSettings, run_dir: Path, model_name: str, settings: Settings) -> PipelineState:
    """
    Запускает пайплайн агентов на задаче проекта и ждёт окончания.

        project: проект и задача пользователя.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        settings: настройки приложения.

    Возвращает: Итоговое состояние пайплайна: папки результатов агентов.
    """
    config = RunnableConfig(
        configurable = {
            PIPELINE_CFG_NAME: PipelineConfig(
                project_path = project.path,
                run_dir = run_dir,
                model_name = model_name,
                settings = settings,
            )
        }
    )
    initial_state = PipelineState(task = project.task, research_dir = None, plan_dir = None)

    return create_pipeline_graph().invoke(input = initial_state, config = config)
