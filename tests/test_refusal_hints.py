"""Тесты хуков подсказки к отказу по пути: подсказка из набора, если в шаге своей фазы были отказы;
подсказка фазы черновика с личной папкой агента."""

from pathlib import Path

from codeteam.core.agent.statistics import DRAFT_PHASE, WORK_PHASE
from codeteam.core.agent.step_hooks import StepContext, draft_phase_hint_hook, refusal_hint_hook
from codeteam.core.tools.files import PathRefusal

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "agent"

# Подсказки к отказу в тестах.
HINTS = ("пояснение-один", "пояснение-два")

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


def test_refusals_in_own_phase_get_one_hint(tmp_path: Path) -> None:
    """
    Отказы чтения и записи в шаге своей фазы — одна подсказка из набора.
    """
    hook = refusal_hint_hook(phase = WORK_PHASE, hints = HINTS)
    for refusals in ((READ_REFUSAL,), (WRITE_REFUSAL,), (READ_REFUSAL, WRITE_REFUSAL)):
        remark = hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = refusals))

        assert remark in HINTS


def test_step_without_refusals_gets_no_hint(tmp_path: Path) -> None:
    """
    Шаг без отказов — без подсказки.
    """
    hook = refusal_hint_hook(phase = WORK_PHASE, hints = HINTS)

    assert hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = ())) is None


def test_refusals_in_other_phase_get_no_hint(tmp_path: Path) -> None:
    """
    Отказы в шаге другой фазы — без подсказки.
    """
    hook = refusal_hint_hook(phase = DRAFT_PHASE, hints = HINTS)

    assert hook(_context(tmp_path = tmp_path, phase = WORK_PHASE, refusals = (READ_REFUSAL,))) is None


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
