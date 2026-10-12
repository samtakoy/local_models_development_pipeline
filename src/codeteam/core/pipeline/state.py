"""Состояние пайплайна и настройки его запуска."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from codeteam.app.settings import Settings

# Ключ настроек пайплайна в configurable настроек запуска графа.
PIPELINE_CFG_NAME = "pipeline"


@dataclass(frozen = True)
class Stages:
    """
    Этапы плана архитектора и ход по ним.

        files: файлы этапов из черновика архитектора по порядку имён и этапы исправлений после них.
        started: сколько этапов начато; текущий этап - последний начатый.
        plan_dir: папка плана сеньора текущего этапа; None, пока он не отработал.
        fix_rounds: сколько этапов исправлений добавила итоговая приёмка.
    """

    files: tuple[Path, ...]
    started: int
    plan_dir: Path | None
    fix_rounds: int

    @property
    def current_file(self) -> Path:
        """Файл текущего этапа: последнего начатого."""
        return self.files[self.started - 1]

    @property
    def has_unstarted(self) -> bool:
        """Есть этапы, которые ещё не начаты."""
        return self.started < len(self.files)


@dataclass(frozen = True)
class Review:
    """
    Последнее ревью работы роли: счёт кругов ревью.

        target: имя роли, чью работу проверил ревьюер.
        round: номер круга ревью, с 1.
        accepted: вердикт: True — работа принята, False — на доработку.
    """

    target: str
    round: int
    accepted: bool


@dataclass(frozen = True)
class Rework:
    """
    Возврат работы роли: его создаёт тот, кто возвращает; узел роли после своей работы сбрасывает его.

        target: имя роли, которой возвращена работа.
        remarks_dir: папка с замечаниями для неё.
        preserve_draft: перенести в новую папку роли черновик из её прошлой папки.
        preserve_context: перенести в новую папку роли файл контекста из её прошлой папки.
    """

    target: str
    remarks_dir: Path
    preserve_draft: bool
    preserve_context: bool


class PipelineState(TypedDict):
    """
    Состояние пайплайна.

        task: задача пользователя.
        requirements_dir: папка черновика менеджера продукта: чеклист требований; None, пока он не отработал.
        requirements_file: файл чеклиста требований; None, пока менеджер продукта не отработал.
        research_dir: папка черновика исследователя; None, пока он не отработал.
        plan_dir: папка черновика архитектора: общее решение и файлы этапов; None, пока он не отработал.
        architecture_file: файл общего решения архитектора; None, пока он не отработал.
        stages: этапы плана архитектора и ход по ним; None, пока архитектор не отработал.
        review: последнее ревью; None, пока ревьюеры не работали.
        rework: возврат работы роли; None, если возврата нет.
        tester_dir: папка черновика последней проверки тестировщика: вердикт и отчёт; None, пока он не работал.
        web_tester_dir: папка черновика последней проверки веб-тестировщика: вердикт и отчёт; None, пока он
            не работал.
        acceptance_dir: папка черновика последней итоговой приёмки: вердикт и план доработки; None, пока она
            не работала.
        next_role: роль, которую пайплайн запустит следующей; None - пайплайн закончен.
        journal_name: имя журнала последней отработавшей роли без расширения; None, пока роли не работали.
        journal_count: число журналов агентов, уже начатых в прогоне.
    """

    task: str
    requirements_dir: Path | None
    requirements_file: Path | None
    research_dir: Path | None
    plan_dir: Path | None
    architecture_file: Path | None
    stages: Stages | None
    review: Review | None
    rework: Rework | None
    tester_dir: Path | None
    web_tester_dir: Path | None
    acceptance_dir: Path | None
    next_role: str | None
    journal_name: str | None
    journal_count: int


@dataclass(frozen = True)
class PipelineConfig:
    """
    Настройки запуска пайплайна.

        project_path: папка рабочего проекта.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        roles: последовательность ролей пайплайна.
        browser_check: проверка приложения в браузере: веб-тестировщик и инструмент check_in_browser.
        library_docs: советник по документации библиотек: инструмент query_library_docs.
        settings: настройки приложения.
    """

    project_path: str
    run_dir: Path
    model_name: str
    roles: tuple[str, ...]
    browser_check: bool
    library_docs: bool
    settings: Settings
