"""Тесты выбора следующей роли пайплайна и проверки списка ролей."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.app.config import load_project_config
from codeteam.core.pipeline import graph as graph_module
from codeteam.core.pipeline.graph import DEFAULT_ROLES, check_roles, choose_next_role, create_pipeline_graph
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Rework, Stages
from codeteam.core.roles.common import PipelineError

# Полный список ролей.
FULL_ROLES = DEFAULT_ROLES

# Список ролей без ревьюеров и веб-тестировщика.
NO_REVIEW_ROLES = ("pm", "researcher", "architect", "senior", "developer")


def _state(*, started: int, total: int, rework: Rework | None) -> PipelineState:
    """
    Собирает состояние пайплайна с этапами и возвратом работы.

        started: сколько этапов начато.
        total: сколько всего этапов.
        rework: возврат работы.

    Возвращает: Состояние пайплайна.
    """
    stages = Stages(
        files = tuple(Path(f"{number}0_stage.md") for number in range(1, total + 1)),
        started = started,
        plan_dir = None,
        fix_rounds = 0,
    )

    return PipelineState(
        task = "задача",
        requirements_dir = None,
        requirements_file = None,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = stages,
        review = None,
        rework = rework,
        next_role = None,
        journal_count = 0,
    )


def _rework(*, target: str) -> Rework:
    """
    Собирает возврат работы роли.

        target: роль, которой возвращена работа.

    Возвращает: Возврат работы.
    """
    return Rework(target = target, remarks_dir = Path("remarks"), preserve_draft = True, preserve_context = True)


@pytest.mark.parametrize(
    ("current", "expected"),
    [("pm", "researcher"), ("researcher", "architect"), ("architect", "architect_review"), ("senior", "developer")],
)
def test_next_by_list(current: str, expected: str) -> None:
    """
    Без возврата и вне конца этапа следующая роль - следующая по списку.
    """
    state = _state(started = 1, total = 3, rework = None)

    assert choose_next_role(roles = FULL_ROLES, current = current, state = state) == expected


def test_rework_goes_to_nearest_target() -> None:
    """
    Возврат работы ведёт к роли-цели перед текущей.
    """
    state = _state(started = 1, total = 3, rework = _rework(target = "developer"))

    assert choose_next_role(roles = FULL_ROLES, current = "developer_review", state = state) == "developer"


def test_rework_to_missing_target_fails() -> None:
    """
    Возврат роли, которой нет перед текущей, - ошибка.
    """
    state = _state(started = 1, total = 3, rework = _rework(target = "web_tester"))

    with pytest.raises(PipelineError):
        choose_next_role(roles = FULL_ROLES, current = "developer_review", state = state)


def test_architect_review_leads_to_first_stage() -> None:
    """
    После принятого ревью архитектора - сеньор первого этапа.
    """
    state = _state(started = 0, total = 3, rework = None)

    assert choose_next_role(roles = FULL_ROLES, current = "architect_review", state = state) == "senior"


def test_stage_end_loops_while_stages_left() -> None:
    """
    После приёмки этапа - сеньор, пока есть неначатые этапы; после последнего этапа - веб-тестировщик.
    """
    middle = _state(started = 2, total = 3, rework = None)
    last = _state(started = 3, total = 3, rework = None)

    assert choose_next_role(roles = FULL_ROLES, current = "developer_review", state = middle) == "senior"
    assert choose_next_role(roles = FULL_ROLES, current = "developer_review", state = last) == "web_tester"


def test_stage_loop_without_review() -> None:
    """
    Без приёмщика этап кончается разработчиком: дальше сеньор или конец пайплайна.
    """
    middle = _state(started = 1, total = 2, rework = None)
    last = _state(started = 2, total = 2, rework = None)

    assert choose_next_role(roles = NO_REVIEW_ROLES, current = "developer", state = middle) == "senior"
    assert choose_next_role(roles = NO_REVIEW_ROLES, current = "developer", state = last) is None


def test_web_tester_fix_stage_loops() -> None:
    """
    После веб-тестировщика: добавлен этап исправлений - сеньор, нет - конец пайплайна.
    """
    with_fix_stage = _state(started = 3, total = 4, rework = None)
    accepted = _state(started = 3, total = 3, rework = None)

    assert choose_next_role(roles = FULL_ROLES, current = "web_tester", state = with_fix_stage) == "senior"
    assert choose_next_role(roles = FULL_ROLES, current = "web_tester", state = accepted) is None


@pytest.mark.parametrize(
    "roles",
    [
        (),
        ("pm", "tester"),
        ("pm", "pm"),
        ("senior", "architect", "developer"),
    ],
)
def test_bad_roles_fail(roles: tuple[str, ...]) -> None:
    """
    Пустой список, неизвестная роль, повтор и разорванные роли этапа - ошибка.
    """
    with pytest.raises(PipelineError):
        check_roles(roles = roles)


@pytest.mark.parametrize("roles", [FULL_ROLES, NO_REVIEW_ROLES])
def test_graph_builds(roles: tuple[str, ...]) -> None:
    """
    Граф собирается для полного списка и для списка без ревьюеров.
    """
    assert create_pipeline_graph(roles = roles) is not None


def test_config_roles(tmp_path: Path) -> None:
    """
    Список ролей берётся из [pipeline] roles; без раздела - список по умолчанию.
    """
    with_roles = tmp_path / "with_roles"
    with_roles.mkdir()
    (with_roles / "set.toml").write_text(
        'project = "/tmp/p"\n[task]\nquestion = "q"\n[pipeline]\nroles = ["pm", "researcher"]\n',
        encoding = "utf-8",
    )
    without_roles = tmp_path / "without_roles"
    without_roles.mkdir()
    (without_roles / "set.toml").write_text('project = "/tmp/p"\n[task]\nquestion = "q"\n', encoding = "utf-8")

    assert load_project_config(setup_dir = str(with_roles)).roles == ("pm", "researcher")
    assert load_project_config(setup_dir = str(without_roles)).roles == DEFAULT_ROLES


def test_graph_runs_roles_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Граф запускает роли по списку, повторяет роли этапа для каждого этапа и возвращает работу по возврату.
    Узлы ролей заменены заглушками: первая приёмка возвращает работу разработчику.
    """
    order: list[str] = []
    review_count = {"developer_review": 0}

    def fake_node(role_name: str):
        """
        Собирает заглушку узла роли.

            role_name: имя роли.

        Возвращает: Узел, который пишет имя роли в порядок запусков и меняет состояние как роль.
        """

        def node(state: PipelineState, config: RunnableConfig) -> dict:
            """Пишет роль в порядок запусков и возвращает обновление состояния этой роли."""
            order.append(role_name)
            if role_name == "architect":
                return {"stages": Stages(files = (Path("10_a.md"), Path("20_b.md")), started = 0, plan_dir = None, fix_rounds = 0)}
            if role_name == "senior":
                stages = state["stages"]
                return {"stages": Stages(files = stages.files, started = stages.started + 1, plan_dir = None, fix_rounds = 0)}
            if role_name == "developer_review":
                review_count["developer_review"] += 1
                rework = _rework(target = "developer") if review_count["developer_review"] == 1 else None
                return {"rework": rework}

            return {"rework": None}

        return node

    for role_name in DEFAULT_ROLES:
        monkeypatch.setitem(graph_module.ROLE_NODES, role_name, fake_node(role_name))

    initial_state = _state(started = 0, total = 0, rework = None)
    initial_state = {**initial_state, "stages": None, "next_role": DEFAULT_ROLES[0]}
    config = RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = "/tmp/project",
        run_dir = Path("/tmp/run"),
        model_name = "model",
        roles = DEFAULT_ROLES,
        settings = None,
    )})
    create_pipeline_graph(roles = DEFAULT_ROLES).invoke(input = initial_state, config = config)

    assert order == [
        "pm", "researcher", "architect", "architect_review",
        "senior", "developer", "developer_review", "developer", "developer_review",
        "senior", "developer", "developer_review",
        "web_tester",
    ]
