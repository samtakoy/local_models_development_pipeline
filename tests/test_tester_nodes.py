"""Тесты узлов тестировщиков: папка отчёта в своём поле состояния, этапы не меняются."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Stages
from codeteam.core.roles.common import REWORK_VERDICT, VERDICT_FILE_NAME
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME
from codeteam.core.roles.tester import node as tester_node_module
from codeteam.core.roles.web_tester import node as web_tester_node_module


def _fake_run_role(*, project_dir: Path):
    """
    Собирает заглушку запуска роли: кладёт в черновик вердикт FIX.

        project_dir: папка проекта.

    Возвращает: Заглушку run_role.
    """

    def run_role(**arguments) -> Path:
        """Пишет вердикт FIX в черновик личной папки роли."""
        answer_dir = draft_dir(private_dir = project_dir / PRIVATE_ROOT / arguments["private_dir_name"])
        answer_dir.mkdir(parents = True, exist_ok = True)
        (answer_dir / VERDICT_FILE_NAME).write_text(f"{REWORK_VERDICT}\nне работает FR1\n", encoding = "utf-8")

        return answer_dir

    return run_role


@pytest.mark.parametrize(
    ("node_module", "node", "own_field", "other_field"),
    [
        (tester_node_module, tester_node_module.tester_node, "tester_dir", "web_tester_dir"),
        (web_tester_node_module, web_tester_node_module.web_tester_node, "web_tester_dir", "tester_dir"),
    ],
)
def test_tester_writes_own_field_without_fix_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    node_module,
    node,
    own_field: str,
    other_field: str,
) -> None:
    """Вердикт FIX: папка отчёта в поле своей роли, поле другого тестировщика и этапы не меняются."""
    monkeypatch.setattr(node_module, "run_role", _fake_run_role(project_dir = tmp_path))
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / REQUIREMENTS_FILE_NAME).write_text("- FR1\n", encoding = "utf-8")
    stages = Stages(files = (tmp_path / "100_stage.md",), started = 1, plan_dir = None, fix_rounds = 0)
    config = RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = str(tmp_path),
        run_dir = tmp_path / "run",
        model_name = "model",
        roles = ("tester", "web_tester"),
        browser_check = True,
        library_docs = False,
        settings = None,
    )})
    state = PipelineState(
        task = "задача",
        requirements_dir = requirements_dir,
        requirements_file = requirements_dir / REQUIREMENTS_FILE_NAME,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = stages,
        review = None,
        rework = None,
        tester_dir = None,
        web_tester_dir = None,
        acceptance_dir = None,
        next_role = "tester",
        journal_name = None,
        journal_count = 0,
    )

    update = node(state, config)

    assert (update[own_field] / VERDICT_FILE_NAME).is_file()
    assert other_field not in update
    assert "stages" not in update
