"""Тесты итоговой приёмки: пропуск без отчётов, вердикт, этап исправлений по плану доработки и его пределы."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.answer_checks import AnswerContext
from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Stages
from codeteam.core.roles.acceptance import acceptance_node, write_acceptance_report
from codeteam.core.roles.acceptance import node as acceptance_node_module
from codeteam.core.roles.acceptance.checks import FIX_PLAN_FILE_NAME, fix_plan_check
from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME

# План доработки в черновике заглушки приёмки.
FIX_PLAN = "## FR1 — Добавление записи\nНадо исправить: запись не добавляется."

# Роли пайплайна с ролями этапа.
STAGE_ROLES = ("senior", "developer", "developer_review", "tester", "acceptance")


class FakeRunRole:
    """
    Заглушка запуска итоговой приёмки: записывает вызов и кладёт в черновик вердикт и план доработки.
    """

    def __init__(self, *, project_dir: Path, verdict: str) -> None:
        self.project_dir = project_dir
        self.verdict = verdict
        self.calls: list[dict] = []

    def __call__(self, **arguments) -> Path:
        """
        Пишет вердикт и, при FIX, план доработки в черновик личной папки роли.

            arguments: аргументы run_role.

        Возвращает: Папку черновика.
        """
        self.calls.append(arguments)
        answer_dir = draft_dir(private_dir = self.project_dir / PRIVATE_ROOT / arguments["private_dir_name"])
        answer_dir.mkdir(parents = True, exist_ok = True)
        (answer_dir / VERDICT_FILE_NAME).write_text(f"{self.verdict}\nитог\n", encoding = "utf-8")
        if self.verdict == REWORK_VERDICT:
            (answer_dir / FIX_PLAN_FILE_NAME).write_text(FIX_PLAN, encoding = "utf-8")

        return answer_dir


def _fake(*, monkeypatch: pytest.MonkeyPatch, project_dir: Path, verdict: str) -> FakeRunRole:
    """
    Подменяет запуск роли в узле итоговой приёмки.

        monkeypatch: подмена объектов теста.
        project_dir: папка проекта.
        verdict: вердикт, который запишет заглушка.

    Возвращает: Заглушку запуска роли.
    """
    fake = FakeRunRole(project_dir = project_dir, verdict = verdict)
    monkeypatch.setattr(acceptance_node_module, "run_role", fake)

    return fake


def _config(*, project_dir: Path, roles: tuple[str, ...]) -> RunnableConfig:
    """
    Собирает настройки запуска графа.

        project_dir: папка проекта.
        roles: роли пайплайна.

    Возвращает: Настройки запуска графа.
    """
    return RunnableConfig(configurable = {PIPELINE_CFG_NAME: PipelineConfig(
        project_path = str(project_dir),
        run_dir = project_dir / "run",
        model_name = "model",
        roles = roles,
        browser_check = True,
        library_docs = False,
        settings = None,
    )})


def _state(*, project_dir: Path, with_reports: bool, fix_rounds: int) -> PipelineState:
    """
    Собирает состояние после тестировщиков.

        project_dir: папка проекта.
        with_reports: тестировщик и веб-тестировщик отработали.
        fix_rounds: сколько этапов исправлений уже добавлено.

    Возвращает: Состояние пайплайна.
    """
    requirements_dir = project_dir / "requirements"
    requirements_dir.mkdir(exist_ok = True)
    (requirements_dir / REQUIREMENTS_FILE_NAME).write_text("- FR1\n", encoding = "utf-8")

    return PipelineState(
        task = "задача",
        requirements_dir = requirements_dir,
        requirements_file = requirements_dir / REQUIREMENTS_FILE_NAME,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = Stages(files = (project_dir / "100_stage.md",), started = 1, plan_dir = None, fix_rounds = fix_rounds),
        review = None,
        rework = None,
        tester_dir = project_dir / "tester" if with_reports else None,
        web_scenarios_dir = None,
        web_tester_dir = project_dir / "web_tester" if with_reports else None,
        acceptance_dir = None,
        next_role = "acceptance",
        journal_name = None,
        journal_count = 3,
    )


def test_no_reports_skips_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Отчётов тестировщиков нет — агент не запускается, состояние не меняется."""
    fake = _fake(monkeypatch = monkeypatch, project_dir = tmp_path, verdict = ACCEPTED_VERDICT)

    update = acceptance_node(
        _state(project_dir = tmp_path, with_reports = False, fix_rounds = 0),
        _config(project_dir = tmp_path, roles = STAGE_ROLES),
    )

    assert update == {}
    assert fake.calls == []


def test_acceptance_reads_reports_without_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Приёмка получает чеклист и отчёты обоих тестировщиков входными папками, проект ей закрыт."""
    fake = _fake(monkeypatch = monkeypatch, project_dir = tmp_path, verdict = ACCEPTED_VERDICT)
    state = _state(project_dir = tmp_path, with_reports = True, fix_rounds = 0)

    acceptance_node(state, _config(project_dir = tmp_path, roles = STAGE_ROLES))

    call = fake.calls[0]
    assert call["input_dirs"] == (state["requirements_dir"], state["tester_dir"], state["web_tester_dir"])
    assert call["extra_readable_dirs"] == ()
    assert call["extra_writable_dirs"] == ()


def test_pass_adds_no_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Вердикт PASS — папка приёмки в состоянии, этапы не меняются."""
    _fake(monkeypatch = monkeypatch, project_dir = tmp_path, verdict = ACCEPTED_VERDICT)

    update = acceptance_node(
        _state(project_dir = tmp_path, with_reports = True, fix_rounds = 0),
        _config(project_dir = tmp_path, roles = STAGE_ROLES),
    )

    assert (update["acceptance_dir"] / VERDICT_FILE_NAME).is_file()
    assert "stages" not in update


def test_fix_adds_stage_with_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Вердикт FIX — в конец этапов добавлен этап исправлений с номером после наибольшего и планом внутри."""
    _fake(monkeypatch = monkeypatch, project_dir = tmp_path, verdict = REWORK_VERDICT)

    update = acceptance_node(
        _state(project_dir = tmp_path, with_reports = True, fix_rounds = 0),
        _config(project_dir = tmp_path, roles = STAGE_ROLES),
    )

    stages = update["stages"]
    fix_stage_file = stages.files[-1]
    assert len(stages.files) == 2
    assert stages.fix_rounds == 1
    assert fix_stage_file.name == "101_fix_1.md"
    assert FIX_PLAN in fix_stage_file.read_text(encoding = "utf-8")


@pytest.mark.parametrize(
    ("roles", "fix_rounds"),
    [(STAGE_ROLES, acceptance_node_module.FIX_ROUND_LIMIT), (("tester", "acceptance"), 0)],
)
def test_fix_without_rounds_or_stage_roles_adds_no_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    roles: tuple[str, ...],
    fix_rounds: int,
) -> None:
    """Вердикт FIX, но круги кончились или ролей этапа нет — этап не добавлен, план доработки в папке приёмки."""
    _fake(monkeypatch = monkeypatch, project_dir = tmp_path, verdict = REWORK_VERDICT)

    update = acceptance_node(
        _state(project_dir = tmp_path, with_reports = True, fix_rounds = fix_rounds),
        _config(project_dir = tmp_path, roles = roles),
    )

    assert "stages" not in update
    assert (update["acceptance_dir"] / FIX_PLAN_FILE_NAME).is_file()


@pytest.mark.parametrize(
    ("verdict", "with_plan", "has_remark"),
    [(REWORK_VERDICT, False, True), (REWORK_VERDICT, True, False), (ACCEPTED_VERDICT, False, False)],
)
def test_fix_plan_check(tmp_path: Path, verdict: str, with_plan: bool, has_remark: bool) -> None:
    """Сдача приёмки: замечание только при вердикте FIX без плана доработки."""
    (tmp_path / VERDICT_FILE_NAME).write_text(f"{verdict}\nитог\n", encoding = "utf-8")
    if with_plan:
        (tmp_path / FIX_PLAN_FILE_NAME).write_text(FIX_PLAN, encoding = "utf-8")

    remark = fix_plan_check(AnswerContext(project_dir = tmp_path, draft_dir = tmp_path))

    assert (remark is not None) == has_remark


@pytest.mark.parametrize(
    ("names", "expected"),
    [(("001_parser.md", "005_viewer.md"), "006"), (("100_a.md", "200_b.md", "201_fix_1.md"), "202"), (("9_a.md",), "10")],
)
def test_next_stage_number(names: tuple[str, ...], expected: str) -> None:
    """Номер этапа исправлений — наибольший номер плюс один, с тем же числом цифр."""
    stage_files = tuple(Path(name) for name in names)

    assert acceptance_node_module._next_stage_number(stage_files = stage_files) == expected


def test_acceptance_report_joins_verdict_and_plan(tmp_path: Path) -> None:
    """Отчёт приёмки в папке прогона — вердикт и план доработки одним файлом."""
    acceptance_dir = tmp_path / "acceptance"
    acceptance_dir.mkdir()
    (acceptance_dir / VERDICT_FILE_NAME).write_text(f"{REWORK_VERDICT}\nитог\n", encoding = "utf-8")
    (acceptance_dir / FIX_PLAN_FILE_NAME).write_text(FIX_PLAN, encoding = "utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    report_file = write_acceptance_report(run_dir = run_dir, acceptance_dir = acceptance_dir)

    report = report_file.read_text(encoding = "utf-8")
    assert report_file.parent == run_dir
    assert report.startswith(REWORK_VERDICT)
    assert FIX_PLAN in report
