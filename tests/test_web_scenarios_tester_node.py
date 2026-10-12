"""Тесты узла проверки по сценариям: прогон сценариев, оценщик без доступа к проекту, ошибки входа."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.common import PipelineError
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME
from codeteam.core.roles.web_scenarios.launch import LAUNCH_FILE_NAME
from codeteam.core.roles.web_scenarios_tester import node as node_module
from codeteam.core.roles.web_scenarios_tester import web_scenarios_tester_node


def _state(*, project_dir: Path, launch: str | None) -> PipelineState:
    """
    Собирает состояние после составителя сценариев.

        project_dir: папка проекта.
        launch: текст файла запуска; None — составитель не работал.

    Возвращает: Состояние пайплайна.
    """
    requirements_dir = project_dir / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / REQUIREMENTS_FILE_NAME).write_text("- FR1\n", encoding = "utf-8")
    scenarios_dir = None
    if launch is not None:
        scenarios_dir = project_dir / PRIVATE_ROOT / "web_scenarios_r1" / "draft"
        scenarios_dir.mkdir(parents = True)
        (scenarios_dir / LAUNCH_FILE_NAME).write_text(launch, encoding = "utf-8")
        (scenarios_dir / "100_add.md").write_text("# Добавление\n", encoding = "utf-8")

    return PipelineState(
        task = "задача",
        requirements_dir = requirements_dir,
        requirements_file = requirements_dir / REQUIREMENTS_FILE_NAME,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = None,
        review = None,
        rework = None,
        tester_dir = None,
        web_scenarios_dir = scenarios_dir,
        web_tester_dir = None,
        web_scenarios_tester_dir = None,
        acceptance_dir = None,
        next_role = "web_scenarios_tester",
        journal_name = None,
        journal_count = 5,
    )


def project_dir_not_readable(*, readable_dirs: tuple[Path, ...], project_dir: Path) -> bool:
    """
    Проверяет, что среди папок чтения нет самой папки проекта.

        readable_dirs: папки чтения агента.
        project_dir: папка проекта.

    Возвращает: True, если папки проекта среди них нет.
    """
    return project_dir.resolve() not in (folder.resolve() for folder in readable_dirs)


def _config(*, project_dir: Path) -> RunnableConfig:
    """
    Собирает настройки запуска графа.

        project_dir: папка проекта.

    Возвращает: Настройки запуска графа.
    """
    return RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = str(project_dir),
        run_dir = project_dir / "run",
        model_name = "model",
        roles = ("web_scenarios", "web_scenarios_tester"),
        browser_check = True,
        library_docs = False,
        settings = None,
    )})


def test_scenarios_run_then_evaluator_without_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Сценарии прогоняются с командой из файла запуска, оценщик получает при разогреве только чеклист,
    сценарии и наблюдения ему открыты для чтения, проект закрыт; папка его ответа — в своём поле состояния."""
    runs = []
    roles = []

    def fake_run_scenarios(**arguments) -> Path:
        """Запоминает прогон и возвращает папку наблюдений."""
        runs.append(arguments)
        observations_dir = tmp_path / PRIVATE_ROOT / arguments["private_dir_name"] / "observations"
        observations_dir.mkdir(parents = True)

        return observations_dir

    def fake_run_role(**arguments) -> Path:
        """Запоминает запуск оценщика и возвращает его черновик."""
        roles.append(arguments)
        answer_dir = draft_dir(private_dir = tmp_path / PRIVATE_ROOT / arguments["private_dir_name"])
        answer_dir.mkdir(parents = True, exist_ok = True)

        return answer_dir

    monkeypatch.setattr(node_module, "run_scenarios", fake_run_scenarios)
    monkeypatch.setattr(node_module, "run_role", fake_run_role)
    state = _state(project_dir = tmp_path, launch = "command: uv run app\nurl: http://127.0.0.1:8050/\n")

    update = web_scenarios_tester_node(state, _config(project_dir = tmp_path))

    assert runs[0]["launch"].command == "uv run app"
    assert [path.name for path in runs[0]["scenario_paths"]] == ["100_add.md"]
    evaluator = roles[0]
    assert evaluator["input_dirs"] == (state["requirements_dir"],)
    assert evaluator["extra_readable_dirs"][0] == state["web_scenarios_dir"]
    assert evaluator["extra_readable_dirs"][1].name == "observations"
    assert project_dir_not_readable(readable_dirs = evaluator["extra_readable_dirs"], project_dir = tmp_path)
    expected_dir = draft_dir(private_dir = tmp_path / PRIVATE_ROOT / "web_scenarios_tester_r1")
    assert update["web_scenarios_tester_dir"] == expected_dir


@pytest.mark.parametrize("launch", [None, "url: http://127.0.0.1:8050/\n"])
def test_missing_scenarios_or_bad_launch_stops_pipeline(tmp_path: Path, launch: str | None) -> None:
    """Составитель не работал или файл запуска не читается — ошибка пайплайна."""
    with pytest.raises(PipelineError):
        web_scenarios_tester_node(_state(project_dir = tmp_path, launch = launch), _config(project_dir = tmp_path))
