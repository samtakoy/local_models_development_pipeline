"""Тесты хуков подсказки к отказу по пути: подсказка помощника с браузером в фазе работы; подсказка фазы
черновика с личной папкой агента и правильным путём своего файла; правильный путь своего файла в фазе работы,
когда проект только для чтения."""

from pathlib import Path

from codeteam.core.agent.statistics import DRAFT_PHASE, WORK_PHASE
from codeteam.core.agent.step_hooks import StepContext, draft_phase_hint_hook, readonly_work_phase_hint_hook
from codeteam.core.roles.browser_checker.hooks import browser_checker_refusal_hook
from codeteam.core.roles.browser_checker.prompts import BROWSER_CHECKER_REFUSAL_HINTS
from codeteam.core.tools.files import PathRefusal

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "agent"

# Отказ чтения по пути вне доступных папок.
READ_REFUSAL = PathRefusal(path = "src/app.py", is_write = False)

# Отказ записи по пути вне доступных папок.
WRITE_REFUSAL = PathRefusal(path = "src/app.py", is_write = True)


def _context(*, tmp_path: Path, phase: str, refusals: tuple[PathRefusal, ...]) -> StepContext:
    """
    Собирает шаг инструментов без изменённых файлов.

        tmp_path: папка проекта теста.
        phase: фаза работы агента.
        refusals: отказы по пути за шаг.

    Возвращает: Шаг инструментов.
    """
    return StepContext(
        project_dir = tmp_path,
        private_dir = tmp_path / RELATIVE_PRIVATE_DIR,
        phase = phase,
        changed_files = (),
        refusals = refusals,
    )


def test_browser_checker_refusals_in_work_phase_get_one_hint(tmp_path: Path) -> None:
    """
    Отказы чтения и записи в шаге фазы работы — одна из подсказок помощника с браузером.
    """
    for refusals in ((READ_REFUSAL,), (WRITE_REFUSAL,), (READ_REFUSAL, WRITE_REFUSAL)):
        remark = browser_checker_refusal_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = refusals))

        assert remark in BROWSER_CHECKER_REFUSAL_HINTS


def test_browser_checker_step_without_refusals_gets_no_hint(tmp_path: Path) -> None:
    """
    Шаг фазы работы без отказов — без подсказки помощника с браузером.
    """
    assert browser_checker_refusal_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = ())) is None


def test_browser_checker_refusals_in_draft_phase_get_no_hint(tmp_path: Path) -> None:
    """
    Отказы в шаге фазы черновика — без подсказки помощника с браузером.
    """
    context = _context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (READ_REFUSAL,))

    assert browser_checker_refusal_hook(context) is None


def test_draft_phase_refusal_gets_hint_with_private_dir(tmp_path: Path) -> None:
    """
    Отказ в шаге фазы черновика — подсказка с личной папкой агента относительно папки проекта.
    """
    remark = draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (WRITE_REFUSAL,)))

    assert remark is not None
    assert RELATIVE_PRIVATE_DIR.as_posix() in remark
    assert str(tmp_path) not in remark


def test_draft_phase_hint_only_for_draft_refusals(tmp_path: Path) -> None:
    """
    Отказ в фазе работы и шаг черновика без отказов — без подсказки черновика.
    """
    assert draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = (READ_REFUSAL,))) is None
    assert draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = ())) is None


def test_readonly_work_phase_draft_section_gets_draft_path(tmp_path: Path) -> None:
    """
    Отказ записи раздела черновика по имени без папки в фазе работы — путь раздела в черновике под тем же именем.
    """
    refusal = PathRefusal(path = "100_project_overview.md", is_write = True)

    remark = readonly_work_phase_hint_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = (refusal,)))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "draft" / "100_project_overview.md").as_posix() in remark


def test_readonly_work_phase_context_file_gets_context_path(tmp_path: Path) -> None:
    """
    Отказ записи файла контекста не на своём месте в фазе работы — путь файла контекста, без пути в черновике.
    """
    refusal = PathRefusal(path = "notes/context.md", is_write = True)

    remark = readonly_work_phase_hint_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = (refusal,)))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "context.md").as_posix() in remark
    assert (RELATIVE_PRIVATE_DIR / "draft").as_posix() not in remark


def test_readonly_work_phase_each_refusal_gets_own_path(tmp_path: Path) -> None:
    """
    Несколько отказов записи разделов — одна подсказка: путь в черновике для каждого имени.
    """
    refusals = tuple(PathRefusal(path = path, is_write = True) for path in ("100_one.md", "docs/110_two.md"))

    remark = readonly_work_phase_hint_hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = refusals))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "draft" / "100_one.md").as_posix() in remark
    assert (RELATIVE_PRIVATE_DIR / "draft" / "110_two.md").as_posix() in remark
    # правило один раз и строка с путём на каждый отказ
    assert len(remark.splitlines()) == 3


def test_readonly_work_phase_skips_other_refusals(tmp_path: Path) -> None:
    """
    Без подсказки: отказ записи файла, не похожего на свой файл агента; отказ чтения; отказ записи раздела
    в фазе черновика.
    """
    code_refusal = PathRefusal(path = "src/app.py", is_write = True)
    section_read_refusal = PathRefusal(path = "100_one.md", is_write = False)
    section_write_refusal = PathRefusal(path = "100_one.md", is_write = True)

    for phase, refusal in (
        (WORK_PHASE, code_refusal),
        (WORK_PHASE, section_read_refusal),
        (DRAFT_PHASE, section_write_refusal),
    ):
        context = _context(tmp_path = tmp_path, phase = phase, refusals = (refusal,))

        assert readonly_work_phase_hint_hook(context) is None


def test_draft_phase_draft_section_write_gets_draft_path(tmp_path: Path) -> None:
    """
    Отказ записи раздела черновика по имени без папки в фазе черновика — путь раздела в черновике под тем же именем.
    """
    refusal = PathRefusal(path = "100_project_overview.md", is_write = True)

    remark = draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (refusal,)))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "draft" / "100_project_overview.md").as_posix() in remark


def test_draft_phase_context_file_write_gets_context_path(tmp_path: Path) -> None:
    """
    Отказ записи файла контекста не на своём месте в фазе черновика — путь файла контекста.
    """
    refusal = PathRefusal(path = "notes/context.md", is_write = True)

    remark = draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (refusal,)))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "context.md").as_posix() in remark


def test_draft_phase_other_refusals_get_general_hint(tmp_path: Path) -> None:
    """
    Отказ записи файла, не похожего на свой файл агента, и отказ чтения раздела в фазе черновика — общая подсказка,
    без пути раздела в черновике.
    """
    general_remark = draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (WRITE_REFUSAL,)))
    section_read_refusal = PathRefusal(path = "100_one.md", is_write = False)
    read_remark = draft_phase_hint_hook(
        _context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = (section_read_refusal,))
    )

    assert general_remark is not None
    assert read_remark == general_remark
    assert (RELATIVE_PRIVATE_DIR / "draft" / "100_one.md").as_posix() not in read_remark


def test_draft_phase_several_write_refusals_get_one_hint(tmp_path: Path) -> None:
    """
    Несколько отказов записи своих файлов в фазе черновика — одна подсказка: что разрешено один раз и строка
    с путём на каждый файл.
    """
    refusals = (
        PathRefusal(path = "100_one.md", is_write = True),
        PathRefusal(path = "context.md", is_write = True),
        PathRefusal(path = "src/app.py", is_write = True),
    )

    remark = draft_phase_hint_hook(_context(tmp_path = tmp_path, phase = DRAFT_PHASE, refusals = refusals))

    assert remark is not None
    assert (RELATIVE_PRIVATE_DIR / "draft" / "100_one.md").as_posix() in remark
    assert (RELATIVE_PRIVATE_DIR / "context.md").as_posix() in remark
    assert len(remark.splitlines()) == 3
