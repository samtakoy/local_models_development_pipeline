"""Тест возврата работы архитектору: новые папки запусков, перенос черновика, имена журналов, сброс возврата."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.project import ReviewMode, ReviewSettings
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.architect import ARCHITECTURE_FILE_NAME, architect_node
from codeteam.core.roles.architect import node as architect_node_module
from codeteam.core.roles.architect_review import architect_review_node
from codeteam.core.roles.architect_review import node as architect_review_node_module
from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME


class FakeRunRole:
    """
    Заглушка запуска роли: записывает вызовы и кладёт в черновик файлы роли вместо работы агента.
    Ревьюер в первый раз возвращает работу, во второй - принимает.
    """

    def __init__(self, *, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.calls: list[dict] = []
        self.review_count = 0

    def __call__(self, **arguments) -> Path:
        """
        Кладёт файлы роли в черновик её личной папки.

            arguments: аргументы run_role.

        Возвращает: Папку черновика.
        """
        self.calls.append(arguments)
        answer_dir = draft_dir(private_dir = self.project_dir / PRIVATE_ROOT / arguments["private_dir_name"])
        answer_dir.mkdir(parents = True, exist_ok = True)
        if arguments["role"].name == "architect":
            (answer_dir / ARCHITECTURE_FILE_NAME).write_text(f"решение {len(self.calls)}\n", encoding = "utf-8")
            (answer_dir / "100_stage.md").write_text("# Этап\n", encoding = "utf-8")
        else:
            self.review_count += 1
            verdict = REWORK_VERDICT if self.review_count == 1 else ACCEPTED_VERDICT
            (answer_dir / VERDICT_FILE_NAME).write_text(f"{verdict}\n", encoding = "utf-8")

        return answer_dir


@pytest.fixture
def fake_run_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeRunRole:
    """
    Подменяет запуск роли в узлах архитектора и его ревьюера.

    Возвращает: Заглушку запуска роли.
    """
    fake = FakeRunRole(project_dir = tmp_path)
    monkeypatch.setattr(architect_node_module, "run_role", fake)
    monkeypatch.setattr(architect_review_node_module, "run_role", fake)

    return fake


def test_architect_rework_flow(tmp_path: Path, fake_run_role: FakeRunRole) -> None:
    """
    Ревьюер возвращает работу: архитектор получает новую папку с перенесённым черновиком, возврат сбрасывается,
    журналы названы как папки.
    """
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / REQUIREMENTS_FILE_NAME).write_text("- требование\n", encoding = "utf-8")
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    config = RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = str(tmp_path),
        run_dir = tmp_path / "run",
        model_name = "model",
        review = ReviewSettings(architect = ReviewMode.ON, developer = ReviewMode.OFF, web_tester = ReviewMode.OFF),
        settings = None,
    )})
    state = PipelineState(
        task = "задача",
        requirements_dir = requirements_dir,
        research_dir = research_dir,
        plan_dir = None,
        stages = None,
        review = None,
        rework = None,
        journal_count = 0,
    )

    for node in (architect_node, architect_review_node, architect_node, architect_review_node):
        state = {**state, **node(state, config)}
        if node is architect_node:
            assert state["rework"] is None

    names = [call["private_dir_name"] for call in fake_run_role.calls]
    assert names == [Path("architect_r1"), Path("architect_review_r1"), Path("architect_r2"), Path("architect_review_r2")]
    journals = [call["journal_name"] for call in fake_run_role.calls]
    assert journals == ["01_architect_r1", "02_architect_review_r1", "03_architect_r2", "04_architect_review_r2"]

    rework_call = fake_run_role.calls[2]
    remarks_dir = draft_dir(private_dir = tmp_path / PRIVATE_ROOT / "architect_review_r1")
    assert remarks_dir in rework_call["input_dirs"]
    assert str(draft_dir(private_dir = PRIVATE_ROOT / "architect_r2")) in rework_call["task"]

    assert state["plan_dir"] == draft_dir(private_dir = tmp_path / PRIVATE_ROOT / "architect_r2")
    assert state["review"].accepted
    assert state["rework"] is None
