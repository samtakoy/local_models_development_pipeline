"""Тесты личных папок запусков агентов: номера <роль>_rN, перенос черновика и контекста, возврат работы."""

from pathlib import Path

from codeteam.core.agent.workspace import PRIVATE_ROOT, context_path, draft_dir
from codeteam.core.pipeline.state import Review, Rework
from codeteam.core.roles.common import last_private_dir_name, make_rework, reserve_private_dir_name, \
    role_private_dir_name
from codeteam.core.roles.common.review import REVIEW_ROUND_LIMIT

# Папка этапа, внутри которой лежат папки запусков ролей этапа.
STAGE_DIR = Path("s10")


def _reserve(*, project_dir: Path, preserve_draft: bool, preserve_context: bool) -> Path:
    """
    Резервирует следующую папку разработчика этапа.

        project_dir: папка проекта.
        preserve_draft: перенести черновик.
        preserve_context: перенести файл контекста.

    Возвращает: Путь новой папки внутри папки личных папок.
    """
    return reserve_private_dir_name(
        project_dir = project_dir,
        parent = STAGE_DIR,
        role_name = "developer",
        preserve_draft = preserve_draft,
        preserve_context = preserve_context,
    )


def _fill_previous(*, project_dir: Path, private_dir_name: Path) -> None:
    """
    Кладёт в папку запуска раздел черновика и файл контекста.

        project_dir: папка проекта.
        private_dir_name: путь папки запуска внутри папки личных папок.
    """
    private_dir = project_dir / PRIVATE_ROOT / private_dir_name
    draft_dir(private_dir = private_dir).mkdir(parents = True)
    (draft_dir(private_dir = private_dir) / "100_report.md").write_text("отчёт\n", encoding = "utf-8")
    context_path(private_dir = private_dir).write_text("контекст\n", encoding = "utf-8")


def test_numbers_grow_per_role_and_place(tmp_path: Path) -> None:
    """
    Номера запусков считаются отдельно для каждой роли и места: первый запуск - r1, следующий - r2.
    """
    first = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    second = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    reviewer = reserve_private_dir_name(
        project_dir = tmp_path,
        parent = STAGE_DIR,
        role_name = "developer_review",
        preserve_draft = False,
        preserve_context = False,
    )
    root_role = reserve_private_dir_name(
        project_dir = tmp_path,
        parent = Path("."),
        role_name = "developer",
        preserve_draft = False,
        preserve_context = False,
    )

    assert first == STAGE_DIR / "developer_r1"
    assert second == STAGE_DIR / "developer_r2"
    assert reviewer == STAGE_DIR / "developer_review_r1"
    assert root_role == Path("developer_r1")
    assert (tmp_path / PRIVATE_ROOT / second).is_dir()


def test_taken_number_is_skipped(tmp_path: Path) -> None:
    """
    Если папка со следующим номером уже создана, берётся номер после неё.
    """
    _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    (tmp_path / PRIVATE_ROOT / STAGE_DIR / "developer_r2").mkdir()

    reserved = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)

    assert reserved == STAGE_DIR / "developer_r3"


def test_preserve_draft_copies_only_draft(tmp_path: Path) -> None:
    """
    preserve_draft переносит из прошлой папки только черновик.
    """
    first = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    _fill_previous(project_dir = tmp_path, private_dir_name = first)

    second = tmp_path / PRIVATE_ROOT / _reserve(project_dir = tmp_path, preserve_draft = True, preserve_context = False)

    assert (draft_dir(private_dir = second) / "100_report.md").read_text(encoding = "utf-8") == "отчёт\n"
    assert not context_path(private_dir = second).exists()


def test_preserve_context_copies_only_context(tmp_path: Path) -> None:
    """
    preserve_context переносит из прошлой папки только файл контекста.
    """
    first = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    _fill_previous(project_dir = tmp_path, private_dir_name = first)

    second = tmp_path / PRIVATE_ROOT / _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = True)

    assert context_path(private_dir = second).read_text(encoding = "utf-8") == "контекст\n"
    assert not draft_dir(private_dir = second).exists()


def test_first_run_with_flags_is_empty(tmp_path: Path) -> None:
    """
    Без прошлой папки роли переносить нечего: новая папка пустая.
    """
    first = tmp_path / PRIVATE_ROOT / _reserve(project_dir = tmp_path, preserve_draft = True, preserve_context = True)

    assert list(first.iterdir()) == []


def test_rework_of_role_preserves_and_other_role_is_clean(tmp_path: Path) -> None:
    """
    Возврат работы роли переносит её черновик и контекст; для другой роли папка чистая.
    """
    first = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    _fill_previous(project_dir = tmp_path, private_dir_name = first)
    rework = Rework(target = "developer", remarks_dir = tmp_path, preserve_draft = True, preserve_context = True)

    other = role_private_dir_name(project_dir = tmp_path, parent = STAGE_DIR, role_name = "senior", rework = rework)
    returned = role_private_dir_name(project_dir = tmp_path, parent = STAGE_DIR, role_name = "developer", rework = rework)

    assert list((tmp_path / PRIVATE_ROOT / other).iterdir()) == []
    returned_dir = tmp_path / PRIVATE_ROOT / returned
    assert (draft_dir(private_dir = returned_dir) / "100_report.md").is_file()
    assert context_path(private_dir = returned_dir).is_file()


def test_forward_pass_is_clean(tmp_path: Path) -> None:
    """
    Без возврата следующий запуск роли получает чистую папку.
    """
    first = _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    _fill_previous(project_dir = tmp_path, private_dir_name = first)

    next_run = role_private_dir_name(project_dir = tmp_path, parent = STAGE_DIR, role_name = "developer", rework = None)

    assert list((tmp_path / PRIVATE_ROOT / next_run).iterdir()) == []


def test_last_private_dir_name(tmp_path: Path) -> None:
    """
    Последняя папка роли - с наибольшим номером; без запусков - None.
    """
    assert last_private_dir_name(project_dir = tmp_path, parent = STAGE_DIR, role_name = "developer") is None

    _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)
    _reserve(project_dir = tmp_path, preserve_draft = False, preserve_context = False)

    assert last_private_dir_name(project_dir = tmp_path, parent = STAGE_DIR, role_name = "developer") == \
        STAGE_DIR / "developer_r2"


def test_make_rework_for_every_rejected_round(tmp_path: Path) -> None:
    """
    Возврат работы создаётся для непринятой работы на каждом круге ревью, в том числе на последнем;
    для принятой работы возврата нет.
    """
    rejected_first = Review(target = "developer", round = 1, accepted = False)
    rejected_last = Review(target = "developer", round = REVIEW_ROUND_LIMIT, accepted = False)
    accepted = Review(target = "developer", round = 1, accepted = True)
    expected = Rework(target = "developer", remarks_dir = tmp_path, preserve_draft = True, preserve_context = False)

    for rejected in (rejected_first, rejected_last):
        rework = make_rework(review = rejected, remarks_dir = tmp_path, preserve_draft = True, preserve_context = False)

        assert rework == expected
    assert make_rework(review = accepted, remarks_dir = tmp_path, preserve_draft = True, preserve_context = True) is None
