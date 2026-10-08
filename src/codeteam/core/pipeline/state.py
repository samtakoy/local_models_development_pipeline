"""Состояние пайплайна и настройки его запуска."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from codeteam.app.settings import Settings
from codeteam.core.pipeline.project import ReviewSettings

# Ключ настроек пайплайна в configurable настроек запуска графа.
PIPELINE_CFG_NAME = "pipeline"


@dataclass(frozen = True)
class Stages:
    """
    Этапы плана архитектора и ход по ним.

        files: файлы этапов из черновика архитектора по порядку имён.
        index: номер текущего этапа в files, с нуля.
        plan_dir: папка плана сеньора текущего этапа; None, пока он не отработал.
    """

    files: tuple[Path, ...]
    index: int
    plan_dir: Path | None

    @property
    def current_file(self) -> Path:
        """Файл текущего этапа."""
        return self.files[self.index]


@dataclass(frozen = True)
class Review:
    """
    Последнее ревью работы роли.

        target: имя роли, чью работу проверил ревьюер; ей возвращаются замечания.
        remarks_dir: папка черновика ревьюера: вердикт и замечания.
        round: номер круга ревью, с 1.
        accepted: вердикт: True — работа принята, False — на доработку.
    """

    target: str
    remarks_dir: Path
    round: int
    accepted: bool


class PipelineState(TypedDict):
    """
    Состояние пайплайна.

        task: задача пользователя.
        requirements_dir: папка черновика менеджера продукта: чеклист требований; None, пока он не отработал.
        research_dir: папка черновика исследователя; None, пока он не отработал.
        plan_dir: папка черновика архитектора: общее решение и файлы этапов; None, пока он не отработал.
        stages: этапы плана архитектора и ход по ним; None, пока архитектор не отработал.
        review: последнее ревью; None, пока ревьюеры не работали.
        journal_count: число журналов агентов, уже начатых в прогоне.
    """

    task: str
    requirements_dir: Path | None
    research_dir: Path | None
    plan_dir: Path | None
    stages: Stages | None
    review: Review | None
    journal_count: int


@dataclass(frozen = True)
class PipelineConfig:
    """
    Настройки запуска пайплайна.

        project_path: папка рабочего проекта.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        review: режимы ревью ролей.
        settings: настройки приложения.
    """

    project_path: str
    run_dir: Path
    model_name: str
    review: ReviewSettings
    settings: Settings
