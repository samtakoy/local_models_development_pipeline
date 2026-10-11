"""Тесты отказов файловых инструментов по пути: отказ попадает в сборщик с путём и видом доступа,
вызов в доступных папках — не попадает."""

from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, GLOB_TOOL_NAME, GREP_TOOL_NAME, \
    READ_TOOL_NAME, WRITE_TOOL_NAME, PathRefusal, PathRefusals, SeenFiles, build_file_tools

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "agent"

# Файл проекта вне папок, доступных агенту.
OUTSIDE_FILE = "src/app.py"

# Файл личной папки агента.
PRIVATE_FILE = (RELATIVE_PRIVATE_DIR / "draft" / "100_notes.md").as_posix()

# Вызовы с путём вне доступных папок: имя инструмента, аргументы, ожидаемый отказ.
OUTSIDE_CALLS = (
    (READ_TOOL_NAME, {"file_path": OUTSIDE_FILE}, PathRefusal(path = OUTSIDE_FILE, is_write = False)),
    (GLOB_TOOL_NAME, {"pattern": "*.py", "path": "src"}, PathRefusal(path = "src", is_write = False)),
    (GLOB_TOOL_NAME, {"pattern": "*.py"}, PathRefusal(path = ".", is_write = False)),
    (GREP_TOOL_NAME, {"pattern": "print", "path": "src"}, PathRefusal(path = "src", is_write = False)),
    (WRITE_TOOL_NAME, {"file_path": OUTSIDE_FILE, "content": "x"}, PathRefusal(path = OUTSIDE_FILE, is_write = True)),
    (
        EDIT_TOOL_NAME,
        {"file_path": OUTSIDE_FILE, "old_string": "print", "new_string": "say"},
        PathRefusal(path = OUTSIDE_FILE, is_write = True),
    ),
    (DELETE_TOOL_NAME, {"file_path": OUTSIDE_FILE}, PathRefusal(path = OUTSIDE_FILE, is_write = True)),
)

# Вызовы в личной папке, в том числе с ошибкой не по пути: имя инструмента и аргументы.
INSIDE_CALLS = (
    (READ_TOOL_NAME, {"file_path": PRIVATE_FILE}),
    (READ_TOOL_NAME, {"file_path": (RELATIVE_PRIVATE_DIR / "missing.md").as_posix()}),
    (GLOB_TOOL_NAME, {"pattern": "*.md", "path": RELATIVE_PRIVATE_DIR.as_posix()}),
    (GREP_TOOL_NAME, {"pattern": "Заметки", "path": RELATIVE_PRIVATE_DIR.as_posix()}),
    (WRITE_TOOL_NAME, {"file_path": (RELATIVE_PRIVATE_DIR / "draft" / "200_new.md").as_posix(), "content": "x"}),
    (EDIT_TOOL_NAME, {"file_path": PRIVATE_FILE, "old_string": "нет такого", "new_string": "y"}),
    (DELETE_TOOL_NAME, {"file_path": PRIVATE_FILE}),
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """
    Папка проекта с файлом src/app.py и файлом черновика в личной папке агента.

    Возвращает: Путь папки проекта.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / OUTSIDE_FILE).write_text("print(1)\n", encoding = "utf-8")
    (tmp_path / PRIVATE_FILE).parent.mkdir(parents = True)
    (tmp_path / PRIVATE_FILE).write_text("# Заметки\n", encoding = "utf-8")

    return tmp_path


def _tools(*, project_dir: Path, refusals: PathRefusals) -> dict[str, BaseTool]:
    """
    Собирает файловые инструменты рабочего места, где чтение и запись разрешены только в личной папке.

        project_dir: папка проекта.
        refusals: отказы по пути за шаг агента.

    Возвращает: Инструменты по именам.
    """
    private_dir = project_dir / RELATIVE_PRIVATE_DIR
    workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        input_dirs = (),
        readable_dirs = (private_dir,),
        writable_dirs = (private_dir,),
    )
    tools = build_file_tools(workspace = workspace, seen_files = SeenFiles(), refusals = refusals)

    return {tool.name: tool for tool in tools}


@pytest.mark.parametrize(("name", "args", "refusal"), OUTSIDE_CALLS)
def test_outside_path_is_collected(project_dir: Path, name: str, args: dict, refusal: PathRefusal) -> None:
    """
    Вызов с путём вне доступных папок — отказ в сборщике с путём от агента и видом доступа; сборщик после
    take пуст.
    """
    refusals = PathRefusals()
    tools = _tools(project_dir = project_dir, refusals = refusals)

    tools[name].invoke(args)

    assert refusals.take() == (refusal,)
    assert refusals.take() == ()


@pytest.mark.parametrize(("name", "args"), INSIDE_CALLS)
def test_inside_path_is_not_collected(project_dir: Path, name: str, args: dict) -> None:
    """
    Вызов в личной папке, в том числе с ошибкой не по пути, — сборщик пуст.
    """
    refusals = PathRefusals()
    tools = _tools(project_dir = project_dir, refusals = refusals)

    tools[name].invoke(args)

    assert refusals.take() == ()
