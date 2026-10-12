"""Тесты хуков шага ролей: у каждой роли в её описании есть общие хуки — места файлов личной папки
и подсказка фазы черновика; у ролей, которым проект только для чтения, — подсказка пути своего файла в фазе работы."""

from pathlib import Path

import pytest

from codeteam.common.git import commit_all, init_repository
from codeteam.core.agent.answer_files import AnswerFiles
from codeteam.core.agent.statistics import DRAFT_PHASE, WORK_PHASE
from codeteam.core.agent.step_hooks import StepContext, draft_phase_hint_hook, private_file_hook, \
    readonly_work_phase_hint_hook
from codeteam.core.roles.advisor.config import ADVISOR_ROLE
from codeteam.core.roles.architect.config import ARCHITECT_ROLE
from codeteam.core.roles.architect_review.config import ARCHITECT_REVIEW_ROLE
from codeteam.core.roles.browser_checker.config import BROWSER_CHECKER_ROLE
from codeteam.core.roles.common import RoleSettings
from codeteam.core.roles.developer.config import DEVELOPER_ROLE
from codeteam.core.roles.developer_review.config import DEVELOPER_REVIEW_ROLE
from codeteam.core.roles.pm.config import PM_ROLE
from codeteam.core.roles.researcher.config import RESEARCHER_ROLE
from codeteam.core.roles.senior.config import SENIOR_ROLE
from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.web_tester.config import WEB_TESTER_ROLE
from codeteam.core.tools.files import PathRefusal

# Все роли команды.
ROLES = (
    ADVISOR_ROLE,
    ARCHITECT_ROLE,
    ARCHITECT_REVIEW_ROLE,
    BROWSER_CHECKER_ROLE,
    DEVELOPER_ROLE,
    DEVELOPER_REVIEW_ROLE,
    PM_ROLE,
    RESEARCHER_ROLE,
    SENIOR_ROLE,
    TESTER_ROLE,
    WEB_TESTER_ROLE,
)

# Роли, которым проект только для чтения: запись только в личную папку.
READONLY_ROLES = (ARCHITECT_ROLE, ARCHITECT_REVIEW_ROLE, PM_ROLE, RESEARCHER_ROLE, SENIOR_ROLE)

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "agent_r1"


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с коммитом и личной папкой агента: хуки проекта у проверяющих ролей смотрят в git.

    Возвращает: Путь папки проекта.
    """
    for name, value in {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(name, value)

    (tmp_path / "app.py").write_text("print(1)\n", encoding = "utf-8")
    init_repository(project_dir = tmp_path)
    commit_all(project_dir = tmp_path, message = "init")
    (tmp_path / RELATIVE_PRIVATE_DIR).mkdir(parents = True)

    return tmp_path


def _remarks(*, role: RoleSettings, context: StepContext) -> list[str]:
    """
    Запускает все хуки шага роли.

        role: описание роли.
        context: шаг инструментов.

    Возвращает: Замечания хуков по порядку, без пустых.
    """
    return [remark for hook in role.step_hooks if (remark := hook(context)) is not None]


@pytest.mark.parametrize("role", ROLES, ids = [role.name for role in ROLES])
def test_role_gets_draft_phase_hint(project_dir: Path, role: RoleSettings) -> None:
    """
    Отказ по пути в шаге фазы черновика — среди замечаний хуков роли подсказка фазы черновика.
    """
    context = StepContext(
        project_dir = project_dir,
        private_dir = project_dir / RELATIVE_PRIVATE_DIR,
        phase = DRAFT_PHASE,
        changed_files = (),
        refusals = (PathRefusal(path = "app.py", is_write = True),),
    )

    assert draft_phase_hint_hook(context) in _remarks(role = role, context = context)


@pytest.mark.parametrize("role", ROLES, ids = [role.name for role in ROLES])
def test_role_gets_stray_private_file_remark(project_dir: Path, role: RoleSettings) -> None:
    """
    Файл в корне личной папки — среди замечаний хуков роли замечание о месте файла личной папки.
    """
    stray_file = project_dir / RELATIVE_PRIVATE_DIR / "notes.txt"
    stray_file.write_text("заметки\n", encoding = "utf-8")
    context = StepContext(
        project_dir = project_dir,
        private_dir = project_dir / RELATIVE_PRIVATE_DIR,
        phase = WORK_PHASE,
        changed_files = (stray_file,),
        refusals = (),
    )
    stray_remark = private_file_hook(answer_files = AnswerFiles(names = (), only_these = False))(context)

    assert stray_remark is not None
    assert stray_remark in _remarks(role = role, context = context)


@pytest.mark.parametrize("role", READONLY_ROLES, ids = [role.name for role in READONLY_ROLES])
def test_readonly_role_gets_draft_section_path(project_dir: Path, role: RoleSettings) -> None:
    """
    Отказ записи раздела черновика по имени без папки в фазе работы — среди замечаний хуков роли правильный путь.
    """
    context = StepContext(
        project_dir = project_dir,
        private_dir = project_dir / RELATIVE_PRIVATE_DIR,
        phase = WORK_PHASE,
        changed_files = (),
        refusals = (PathRefusal(path = "100_project_overview.md", is_write = True),),
    )
    hint = readonly_work_phase_hint_hook(context)

    assert hint is not None
    assert hint in _remarks(role = role, context = context)
