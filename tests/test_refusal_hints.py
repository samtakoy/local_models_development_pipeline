"""Тесты пояснений к отказу по пути: к отказу дописывается одно пояснение, выбранное по пути."""

from pathlib import Path

import pytest

from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace

# Пояснения к отказу в тестах.
HINTS = ("пояснение-один", "пояснение-два")

# Пути вне доступных папок для тестов.
OUTSIDE_PATHS = tuple(f"src/module_{number}.py" for number in range(20))


def _workspace(*, tmp_path: Path, refusal_hints: tuple[str, ...]) -> Workspace:
    """
    Собирает рабочее место, где чтение и запись разрешены только в личной папке.

        tmp_path: папка проекта теста.
        refusal_hints: пояснения к отказу.

    Возвращает: Рабочее место.
    """
    private_dir = tmp_path / ".ct-work" / "agent"

    return Workspace(
        project_dir = tmp_path,
        private_dir = private_dir,
        input_dirs = (),
        readable_dirs = (private_dir,),
        writable_dirs = (private_dir,),
        refusal_hints = refusal_hints,
    )


def _refusal(*, workspace: Workspace, path: str, is_write: bool) -> str:
    """
    Получает текст отказа по пути.

        workspace: рабочее место.
        path: путь от агента.
        is_write: проверять право записи, иначе право чтения.

    Возвращает: Текст отказа.
    """
    resolve = workspace.resolve_writable if is_write else workspace.resolve_readable
    with pytest.raises(PathOutsideWorkspace) as error:
        resolve(path = path)

    return str(error.value)


@pytest.mark.parametrize("is_write", [False, True])
def test_same_path_gets_same_hint(tmp_path: Path, is_write: bool) -> None:
    """
    Отказ по одному и тому же пути всегда с одним и тем же пояснением из набора.
    """
    workspace = _workspace(tmp_path = tmp_path, refusal_hints = HINTS)
    for path in OUTSIDE_PATHS:
        first = _refusal(workspace = workspace, path = path, is_write = is_write)
        second = _refusal(workspace = workspace, path = path, is_write = is_write)

        assert first == second
        assert sum(hint in first for hint in HINTS) == 1


def test_different_paths_use_all_hints(tmp_path: Path) -> None:
    """
    На разных путях встречаются все пояснения набора.
    """
    workspace = _workspace(tmp_path = tmp_path, refusal_hints = HINTS)
    refusals = [_refusal(workspace = workspace, path = path, is_write = False) for path in OUTSIDE_PATHS]

    assert all(any(hint in refusal for refusal in refusals) for hint in HINTS)


def test_no_hints_gives_bare_refusal(tmp_path: Path) -> None:
    """
    Без пояснений отказ не содержит ни одного из них.
    """
    workspace = _workspace(tmp_path = tmp_path, refusal_hints = ())
    refusal = _refusal(workspace = workspace, path = OUTSIDE_PATHS[0], is_write = False)

    assert not any(hint in refusal for hint in HINTS)
