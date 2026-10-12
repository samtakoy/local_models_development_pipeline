"""Тесты правил черновика ответа в общих инструкциях агента: правила собираются по файлам ответа роли."""

import pytest

from codeteam.core.agent.answer_files import AnswerFiles, build_draft_rules
from codeteam.core.agent.prompts import DRAFT_SECTION_RULES
from codeteam.core.roles.acceptance.config import ACCEPTANCE_ROLE
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
from codeteam.core.roles.web_scenarios.config import WEB_SCENARIOS_ROLE
from codeteam.core.roles.web_scenarios_tester.config import WEB_SCENARIOS_TESTER_ROLE
from codeteam.core.roles.web_tester.config import WEB_TESTER_ROLE

# Папка черновика в тестах, как её видит агент.
SHOWN_DRAFT_DIR = ".ct-work/tester_r1/draft"

# Все роли пайплайна и помощники.
ALL_ROLES = (
    ACCEPTANCE_ROLE,
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
    WEB_SCENARIOS_ROLE,
    WEB_SCENARIOS_TESTER_ROLE,
    WEB_TESTER_ROLE,
)


def _section_rules() -> str:
    """
    Строит правила файлов-разделов для папки черновика тестов.

    Возвращает: Правила файлов-разделов.
    """
    return DRAFT_SECTION_RULES.format(draft_dir = SHOWN_DRAFT_DIR)


def test_role_without_answer_files_gets_section_rules() -> None:
    """Роль без заранее известных файлов ответа получает правила файлов-разделов без добавок."""
    rules = build_draft_rules(answer_files = AnswerFiles(names = (), only_these = False), shown_draft_dir = SHOWN_DRAFT_DIR)

    assert rules == _section_rules()


def test_role_with_required_files_gets_section_rules_and_file_names() -> None:
    """Роль с обязательными файлами ответа получает правила файлов-разделов и имена этих файлов."""
    rules = build_draft_rules(
        answer_files = AnswerFiles(names = ("000_verdict.md", "100_report.md"), only_these = False),
        shown_draft_dir = SHOWN_DRAFT_DIR,
    )

    assert rules.startswith(_section_rules())
    assert "000_verdict.md" in rules
    assert "100_report.md" in rules


def test_role_with_only_answer_files_gets_no_section_rules() -> None:
    """Роль с одними файлами ответа получает имя файла и папку черновика, без правил файлов-разделов."""
    rules = build_draft_rules(
        answer_files = AnswerFiles(names = ("000_observations.md",), only_these = True),
        shown_draft_dir = SHOWN_DRAFT_DIR,
    )

    assert "000_observations.md" in rules
    assert SHOWN_DRAFT_DIR in rules
    assert _section_rules() not in rules


def test_only_answer_files_without_names_is_rejected() -> None:
    """Описание с одними файлами ответа без их имён не создаётся."""
    with pytest.raises(ValueError):
        AnswerFiles(names = (), only_these = True)


@pytest.mark.parametrize("role", ALL_ROLES, ids = lambda role: role.name)
def test_role_rules_name_every_answer_file(role: RoleSettings) -> None:
    """В правилах черновика каждой роли названы все её файлы ответа."""
    rules = build_draft_rules(answer_files = role.answer_files, shown_draft_dir = SHOWN_DRAFT_DIR)

    for file_name in role.answer_files.names:
        assert file_name in rules
