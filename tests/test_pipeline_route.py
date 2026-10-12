"""Тесты выбора следующей роли пайплайна и проверки списка ролей."""

import json
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.app.config import ConfigError, load_project_config
from codeteam.common.git import commit_all, head_commit, init_repository
from codeteam.core.pipeline import graph as graph_module
from codeteam.core.pipeline.graph import DEFAULT_ROLES, check_roles, choose_next_role, create_pipeline_graph
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Review, Rework, Stages
from codeteam.core.pipeline.state_file import load_state, save_state, state_file_path
from codeteam.core.roles.common import PipelineError
from codeteam.core.roles.common.review import REVIEW_ROUND_LIMIT

# Полный список ролей.
FULL_ROLES = DEFAULT_ROLES

# Список ролей без ревьюеров и веб-тестировщика.
NO_REVIEW_ROLES = ("pm", "researcher", "architect", "senior", "developer")

# Полный список ролей с тестировщиком вместо веб-тестировщика.
TESTER_ROLES = (*DEFAULT_ROLES[:-2], "tester", "acceptance")


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
        tester_dir = None,
        web_tester_dir = None,
        acceptance_dir = None,
        next_role = None,
        journal_name = None,
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


def _with_review(*, state: PipelineState, target: str, review_round: int) -> PipelineState:
    """
    Добавляет в состояние непринятое ревью работы роли.

        state: состояние пайплайна.
        target: роль, чью работу проверил ревьюер.
        review_round: номер круга ревью.

    Возвращает: Состояние с ревью.
    """
    return {**state, "review": Review(target = target, round = review_round, accepted = False)}


def test_reviewer_runs_after_rework_while_rounds_left() -> None:
    """
    После доработки по ревью, которое не было последним кругом, снова идёт ревьюер.
    """
    developer_state = _with_review(
        state = _state(started = 1, total = 3, rework = None),
        target = "developer",
        review_round = REVIEW_ROUND_LIMIT - 1,
    )
    architect_state = _with_review(
        state = _state(started = 0, total = 3, rework = None),
        target = "architect",
        review_round = REVIEW_ROUND_LIMIT - 1,
    )

    assert choose_next_role(roles = FULL_ROLES, current = "developer", state = developer_state) == "developer_review"
    assert choose_next_role(roles = FULL_ROLES, current = "architect", state = architect_state) == "architect_review"


def test_reviewer_skipped_after_last_rework() -> None:
    """
    После доработки по последнему кругу ревью ревьюер пропускается: дальше сеньор следующего этапа,
    после последнего этапа - веб-тестировщик; после архитектора - сеньор первого этапа.
    """
    middle = _with_review(
        state = _state(started = 2, total = 3, rework = None),
        target = "developer",
        review_round = REVIEW_ROUND_LIMIT,
    )
    last = _with_review(
        state = _state(started = 3, total = 3, rework = None),
        target = "developer",
        review_round = REVIEW_ROUND_LIMIT,
    )
    architect_state = _with_review(
        state = _state(started = 0, total = 3, rework = None),
        target = "architect",
        review_round = REVIEW_ROUND_LIMIT,
    )

    assert choose_next_role(roles = FULL_ROLES, current = "developer", state = middle) == "senior"
    assert choose_next_role(roles = FULL_ROLES, current = "developer", state = last) == "web_tester"
    assert choose_next_role(roles = FULL_ROLES, current = "architect", state = architect_state) == "senior"


def test_acceptance_fix_stage_loops() -> None:
    """
    После итоговой приёмки: добавлен этап исправлений - сеньор, нет - конец пайплайна.
    После веб-тестировщика - итоговая приёмка.
    """
    with_fix_stage = _state(started = 3, total = 4, rework = None)
    accepted = _state(started = 3, total = 3, rework = None)

    assert choose_next_role(roles = FULL_ROLES, current = "acceptance", state = with_fix_stage) == "senior"
    assert choose_next_role(roles = FULL_ROLES, current = "acceptance", state = accepted) is None
    assert choose_next_role(roles = FULL_ROLES, current = "web_tester", state = accepted) == "acceptance"


@pytest.mark.parametrize(
    "roles",
    [
        (),
        ("pm", "translator"),
        ("pm", "pm"),
        ("senior", "architect", "developer"),
        ("senior", "developer", "acceptance", "tester"),
    ],
)
def test_bad_roles_fail(roles: tuple[str, ...]) -> None:
    """
    Пустой список, неизвестная роль, повтор и разорванные роли этапа - ошибка.
    """
    with pytest.raises(PipelineError):
        check_roles(roles = roles)


@pytest.mark.parametrize("roles", [FULL_ROLES, NO_REVIEW_ROLES, TESTER_ROLES])
def test_graph_builds(roles: tuple[str, ...]) -> None:
    """
    Граф собирается для полного списка, для списка без ревьюеров и для списка с тестировщиком.
    """
    assert create_pipeline_graph(roles = roles) is not None


def _write_set_file(*, setup_dir: Path, pipeline: str) -> str:
    """
    Пишет файл состава с заданным разделом [pipeline].

        setup_dir: папка файла состава.
        pipeline: строки раздела [pipeline].

    Возвращает: Папку файла состава строкой.
    """
    setup_dir.mkdir()
    (setup_dir / "set.toml").write_text(
        f'project = "/tmp/p"\n[task]\nquestion = "q"\n[pipeline]\n{pipeline}',
        encoding = "utf-8",
    )

    return str(setup_dir)


def test_config_roles(tmp_path: Path) -> None:
    """
    Список ролей берётся из [pipeline] roles; без списка - список по умолчанию.
    """
    with_roles = _write_set_file(
        setup_dir = tmp_path / "with_roles",
        pipeline = 'browser_check = true\nlibrary_docs = true\nroles = ["pm", "researcher"]\n',
    )
    without_roles = _write_set_file(
        setup_dir = tmp_path / "without_roles",
        pipeline = "browser_check = true\nlibrary_docs = true\n",
    )

    assert load_project_config(setup_dir = with_roles).roles == ("pm", "researcher")
    assert load_project_config(setup_dir = without_roles).roles == DEFAULT_ROLES


@pytest.mark.parametrize(
    "pipeline",
    [
        "library_docs = true\n",
        'browser_check = "yes"\nlibrary_docs = true\n',
        "browser_check = false\nlibrary_docs = true\n",
        "browser_check = true\n",
        'browser_check = true\nlibrary_docs = "yes"\n',
    ],
)
def test_config_browser_check_error(tmp_path: Path, pipeline: str) -> None:
    """
    Без browser_check или library_docs, с не логическим значением или с browser_check = false при веб-тестировщике
    в списке ролей файл состава не читается.
    """
    with pytest.raises(ConfigError):
        load_project_config(setup_dir = _write_set_file(setup_dir = tmp_path / "setup", pipeline = pipeline))


@pytest.mark.parametrize("roles", ['["pm", "researcher"]', '["pm", "researcher", "tester"]'])
def test_config_browser_check_off(tmp_path: Path, roles: str) -> None:
    """
    browser_check = false читается, если веб-тестировщика нет в списке ролей; тестировщик работает и без браузера.
    """
    setup_dir = _write_set_file(
        setup_dir = tmp_path / "setup",
        pipeline = f"browser_check = false\nlibrary_docs = true\nroles = {roles}\n",
    )

    assert load_project_config(setup_dir = setup_dir).browser_check is False


class FakeRoles:
    """
    Заглушки узлов ролей: пишут порядок запусков и меняют состояние как роли.
    Первая приёмка этапа возвращает работу разработчику.
    """

    def __init__(self) -> None:
        self.order: list[str] = []
        self.review_count = 0

    def node(self, *, role_name: str):
        """
        Собирает заглушку узла роли.

            role_name: имя роли.

        Возвращает: Узел, который пишет имя роли в порядок запусков и возвращает обновление состояния.
        """

        def node(state: PipelineState, config: RunnableConfig) -> dict:
            """Пишет роль в порядок запусков и возвращает обновление состояния этой роли."""
            self.order.append(role_name)
            journal_count = state["journal_count"] + 1
            update = {"rework": None, "journal_name": f"{journal_count:02d}_{role_name}", "journal_count": journal_count}
            if role_name == "architect":
                stages = Stages(files = (Path("10_a.md"), Path("20_b.md")), started = 0, plan_dir = None, fix_rounds = 0)
                return {**update, "stages": stages}
            if role_name == "senior":
                stages = state["stages"]
                stages = Stages(files = stages.files, started = stages.started + 1, plan_dir = None, fix_rounds = 0)
                return {**update, "stages": stages}
            if role_name == "developer_review":
                self.review_count += 1
                return {**update, "rework": _rework(target = "developer") if self.review_count == 1 else None}

            return update

        return node


@pytest.fixture
def fake_roles(monkeypatch: pytest.MonkeyPatch) -> FakeRoles:
    """
    Подменяет узлы всех ролей заглушками.

    Возвращает: Заглушки ролей с порядком запусков.
    """
    fake = FakeRoles()
    for role_name in DEFAULT_ROLES:
        monkeypatch.setitem(graph_module.ROLE_NODES, role_name, fake.node(role_name = role_name))

    return fake


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с репозиторием git и одним коммитом.

    Возвращает: Путь папки проекта.
    """
    for name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(name, "test")
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(name, "test@example.com")

    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# app\n", encoding = "utf-8")
    init_repository(project_dir = project)
    commit_all(project_dir = project, message = "init")

    return project


def _config(*, project_dir: Path, run_dir: Path) -> RunnableConfig:
    """
    Собирает настройки запуска графа с полным списком ролей.

        project_dir: папка проекта с репозиторием git.
        run_dir: папка прогона.

    Возвращает: Настройки запуска графа.
    """
    return RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = str(project_dir),
        run_dir = run_dir,
        model_name = "model",
        roles = DEFAULT_ROLES,
        browser_check = True,
        library_docs = False,
        settings = None,
    )})


def test_graph_runs_roles_in_order(fake_roles: FakeRoles, project_dir: Path, tmp_path: Path) -> None:
    """
    Граф запускает роли по списку, повторяет роли этапа для каждого этапа и возвращает работу по возврату.
    После каждой роли рядом с её журналом лежит снимок; последний говорит, что прогон закончен.
    """
    run_dir = tmp_path / "run"
    initial_state = {**_state(started = 0, total = 0, rework = None), "stages": None, "next_role": DEFAULT_ROLES[0]}

    create_pipeline_graph(roles = DEFAULT_ROLES).invoke(
        input = initial_state,
        config = _config(project_dir = project_dir, run_dir = run_dir),
    )

    assert fake_roles.order == [
        "pm", "researcher", "architect", "architect_review",
        "senior", "developer", "developer_review", "developer", "developer_review",
        "senior", "developer", "developer_review",
        "web_tester", "acceptance",
    ]
    assert len(list(run_dir.glob("*.state.json"))) == len(fake_roles.order)
    last_snapshot = state_file_path(run_dir = run_dir, journal_name = "14_acceptance")
    saved = load_state(path = last_snapshot)
    assert saved["next_role"] is None
    assert saved["stages"].started == 2
    assert json.loads(last_snapshot.read_text(encoding = "utf-8"))["commit"] == head_commit(project_dir = project_dir)


def test_graph_resumes_from_saved_state(fake_roles: FakeRoles, project_dir: Path, tmp_path: Path) -> None:
    """
    Граф, запущенный с сохранённым состоянием, продолжает с его next_role.
    """
    saved_path = state_file_path(run_dir = tmp_path / "first", journal_name = "05_senior")
    save_state(
        state = {**_state(started = 1, total = 2, rework = None), "next_role": "developer", "journal_count": 5},
        commit = head_commit(project_dir = project_dir),
        path = saved_path,
    )
    fake_roles.review_count = 1

    create_pipeline_graph(roles = DEFAULT_ROLES).invoke(
        input = load_state(path = saved_path),
        config = _config(project_dir = project_dir, run_dir = tmp_path / "second"),
    )

    assert fake_roles.order == [
        "developer", "developer_review", "senior", "developer", "developer_review", "web_tester", "acceptance",
    ]
