"""Тесты прогона сценариев: запуск приложения, помощник на каждый сценарий, наблюдения в файлы, уборка проекта."""

import socket
from pathlib import Path

import pytest
from langchain_core.tools import ToolException

from codeteam.common.git import commit_all, init_repository, list_uncommitted_changes
from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.web_scenarios import AppLaunch
from codeteam.core.roles.web_scenarios_tester import runner
from codeteam.core.roles.web_scenarios_tester.runner import LAUNCH_FAILED_FILE_NAME, run_scenarios
from tests.shell_helpers import error_page_server_command, free_port, requires_sandbox

# Личная папка проверки по сценариям внутри папки личных папок.
PRIVATE_DIR_NAME = Path("web_scenarios_tester_r1")


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с репозиторием git, одним коммитом и файлами сценариев.

    Возвращает: Путь папки проекта.
    """
    for name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(name, "test")
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(name, "test@example.com")
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# app\n", encoding = "utf-8")
    (project / ".gitignore").write_text(".ct-work/\ntmp_check/\n", encoding = "utf-8")
    init_repository(project_dir = project)
    commit_all(project_dir = project, message = "init")
    scenarios_dir = project / PRIVATE_ROOT / "web_scenarios_r1" / "draft"
    scenarios_dir.mkdir(parents = True)
    for name in ("100_add.md", "200_open.md"):
        (scenarios_dir / name).write_text(f"# {name}\n1. Открой адрес приложения.\n", encoding = "utf-8")

    return project


def _scenario_paths(*, project_dir: Path) -> list[Path]:
    """
    Находит файлы сценариев проекта теста.

        project_dir: папка проекта.

    Возвращает: Файлы сценариев по порядку имён.
    """
    return sorted((project_dir / PRIVATE_ROOT / "web_scenarios_r1" / "draft").glob("*.md"))


def _run(*, project_dir: Path, launch: AppLaunch) -> Path:
    """
    Прогоняет сценарии проекта теста.

        project_dir: папка проекта.
        launch: команда запуска и адрес приложения.

    Возвращает: Папку наблюдений.
    """
    cfg = PipelineConfig(
        project_path = str(project_dir),
        run_dir = project_dir.parent / "run",
        model_name = "model",
        roles = (),
        browser_check = True,
        library_docs = False,
        settings = None,
    )

    return run_scenarios(
        cfg = cfg,
        caller_name = "web_scenarios_tester",
        private_dir_name = PRIVATE_DIR_NAME,
        journal_name = "25_web_scenarios_tester_r1",
        launch = launch,
        scenario_paths = _scenario_paths(project_dir = project_dir),
    )


def _fake_helper(*, project_dir: Path, failing_scenario: str | None):
    """
    Собирает заглушку помощника с браузером: пишет наблюдения с текстом сценария, как приложение — файл данных
    в проекте и правку отслеживаемого файла.

        project_dir: папка проекта.
        failing_scenario: начало текста сценария, на котором заглушка падает; None — не падает.

    Возвращает: Заглушку run_browser_checker.
    """

    def run_browser_checker(*, caller_context, project_dir, url: str, scenarios: str) -> Path:
        """Пишет наблюдения или падает на заданном сценарии."""
        if failing_scenario is not None and scenarios.startswith(failing_scenario):
            raise ToolException("помощник упал")

        (project_dir / "data.json").write_text("{}", encoding = "utf-8")
        (project_dir / "README.md").write_text("# изменено приложением\n", encoding = "utf-8")
        observations_path = project_dir.parent / "observations.md"
        observations_path.write_text(f"Видел: {scenarios.splitlines()[0]} на {url}", encoding = "utf-8")

        return observations_path

    return run_browser_checker


@requires_sandbox
def test_each_scenario_goes_to_own_helper(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Приложение запущено, каждый сценарий — отдельный помощник, наблюдения под именем файла сценария,
    упавший помощник — ошибка в файле; после прогона приложение остановлено, правки проекта убраны."""
    fake_helper = _fake_helper(project_dir = project_dir, failing_scenario = "# 200")
    monkeypatch.setattr(runner, "run_browser_checker", fake_helper)
    port = free_port()
    launch = AppLaunch(
        command = error_page_server_command(port = port, detached = False),
        url = f"http://127.0.0.1:{port}/",
    )

    observations_dir = _run(project_dir = project_dir, launch = launch)

    assert sorted(path.name for path in observations_dir.iterdir()) == ["100_add.md", "200_open.md"]
    assert "# 100_add.md" in (observations_dir / "100_add.md").read_text(encoding = "utf-8")
    assert "помощник упал" in (observations_dir / "200_open.md").read_text(encoding = "utf-8")
    assert list_uncommitted_changes(project_dir = project_dir) == []
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@requires_sandbox
def test_failed_launch_skips_scenarios(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Приложение не запустилось — помощники не запускаются, в папке наблюдений один файл об ошибке запуска."""
    calls = []
    monkeypatch.setattr(runner, "run_browser_checker", lambda **arguments: calls.append(arguments))
    launch = AppLaunch(command = "exit 3", url = f"http://127.0.0.1:{free_port()}/")

    observations_dir = _run(project_dir = project_dir, launch = launch)

    assert [path.name for path in observations_dir.iterdir()] == [LAUNCH_FAILED_FILE_NAME]
    assert calls == []
