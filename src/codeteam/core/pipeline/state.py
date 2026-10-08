"""Состояние пайплайна и настройки его запуска."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from codeteam.app.settings import Settings

# Ключ настроек пайплайна в configurable настроек запуска графа.
PIPELINE_CFG_NAME = "pipeline"


class PipelineState(TypedDict):
    """
    Состояние пайплайна.

        task: задача пользователя.
        requirements_dir: папка черновика менеджера продукта: чеклист требований; None, пока он не отработал.
        research_dir: папка черновика исследователя; None, пока он не отработал.
        plan_dir: папка черновика архитектора: общее решение и файлы этапов; None, пока он не отработал.
        stage_files: файлы этапов из черновика архитектора по порядку имён.
        stage_index: номер текущего этапа в stage_files, с нуля.
        stage_plan_dir: папка плана сеньора текущего этапа; None, пока он не отработал.
        journal_count: число журналов агентов, уже начатых в прогоне.
    """

    task: str
    requirements_dir: Path | None
    research_dir: Path | None
    plan_dir: Path | None
    stage_files: list[Path]
    stage_index: int
    stage_plan_dir: Path | None
    journal_count: int


@dataclass(frozen = True)
class PipelineConfig:
    """
    Настройки запуска пайплайна.

        project_path: папка рабочего проекта.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        settings: настройки приложения.
    """

    project_path: str
    run_dir: Path
    model_name: str
    settings: Settings
