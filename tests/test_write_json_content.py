"""Тесты write с содержимым-объектом: модель передала JSON объектом, а не текстом."""

import json
from pathlib import Path

from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import WRITE_TOOL_NAME, PathRefusal, PathRefusals, SeenFiles, build_file_tools

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "agent"

# Содержимое файла объектом, как его присылает модель.
JSON_CONTENT = {"topics": ["Default"], "sources": [{"path": "docs/колода.txt"}]}


def _write_tool(*, project_dir: Path, refusals: PathRefusals):
    """
    Собирает write рабочего места, где запись разрешена только в личной папке.

        project_dir: папка проекта.
        refusals: отказы по пути за шаг агента.

    Возвращает: Инструмент write.
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

    return next(tool for tool in tools if tool.name == WRITE_TOOL_NAME)


def test_object_content_is_written_as_json(tmp_path: Path) -> None:
    """Объект в content записан текстом JSON, который читается обратно в тот же объект."""
    file_path = RELATIVE_PRIVATE_DIR / "data.json"

    _write_tool(project_dir = tmp_path, refusals = PathRefusals()).invoke(
        {"file_path": file_path.as_posix(), "content": JSON_CONTENT}
    )

    assert json.loads((tmp_path / file_path).read_text(encoding = "utf-8")) == JSON_CONTENT


def test_object_content_outside_workspace_gets_path_refusal(tmp_path: Path) -> None:
    """Объект в content вне доступных папок — обычный отказ по пути, файла нет."""
    refusals = PathRefusals()

    _write_tool(project_dir = tmp_path, refusals = refusals).invoke(
        {"file_path": "data/library.json", "content": JSON_CONTENT}
    )

    assert refusals.take() == (PathRefusal(path = "data/library.json", is_write = True),)
    assert not (tmp_path / "data" / "library.json").exists()
