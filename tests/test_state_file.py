"""Тесты снимков состояния пайплайна: записанное состояние читается обратно без потерь, коммит лежит рядом."""

import json
from pathlib import Path

from codeteam.core.pipeline.state import PipelineState, Review, Rework, Stages
from codeteam.core.pipeline.state_file import load_state, save_state, state_file_path


def test_full_state_round_trip(tmp_path: Path) -> None:
    """
    Состояние со всеми заполненными полями, этапами, ревью и возвратом читается таким же, каким записано.
    """
    state = PipelineState(
        task = "задача",
        requirements_dir = Path("/p/.ct-work/pm_r1/draft"),
        requirements_file = Path("/p/.ct-work/pm_r1/draft/100_requirements.md"),
        research_dir = Path("/p/.ct-work/researcher_r1/draft"),
        plan_dir = Path("/p/.ct-work/architect_r2/draft"),
        architecture_file = Path("/p/.ct-work/architect_r2/draft/000_architecture.md"),
        stages = Stages(
            files = (Path("/p/a/100_config.md"), Path("/p/a/200_ui.md")),
            started = 1,
            plan_dir = Path("/p/.ct-work/s100/senior_r1/draft"),
            fix_rounds = 0,
        ),
        review = Review(target = "developer", round = 1, accepted = False),
        rework = Rework(
            target = "developer",
            remarks_dir = Path("/p/.ct-work/s100/developer_review_r1/draft"),
            preserve_draft = True,
            preserve_context = False,
        ),
        tester_dir = None,
        web_tester_dir = None,
        next_role = "developer",
        journal_name = "07_s100_developer_review_r1",
        journal_count = 7,
    )
    path = state_file_path(run_dir = tmp_path, journal_name = state["journal_name"])

    save_state(state = state, commit = "abc123", path = path)

    assert path.name == "07_s100_developer_review_r1.state.json"
    assert load_state(path = path) == state
    assert json.loads(path.read_text(encoding = "utf-8"))["commit"] == "abc123"


def test_empty_state_round_trip(tmp_path: Path) -> None:
    """
    Начальное состояние с пустыми полями читается таким же, каким записано; временного файла не остаётся.
    """
    state = PipelineState(
        task = "задача",
        requirements_dir = None,
        requirements_file = None,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = None,
        review = None,
        rework = None,
        tester_dir = None,
        web_tester_dir = None,
        next_role = "pm",
        journal_name = None,
        journal_count = 0,
    )
    path = tmp_path / "run" / "01_pm_r1.state.json"

    save_state(state = state, commit = "abc123", path = path)

    assert load_state(path = path) == state
    assert [file.name for file in path.parent.iterdir()] == ["01_pm_r1.state.json"]
