"""Тесты инструмента edit вместе с read и write."""

from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import PathRefusals, SeenFiles, build_file_tools
from codeteam.core.tools.files.edit_prompts import (
    EMPTY_OLD_STRING_MESSAGE,
    IDENTICAL_STRINGS_MESSAGE,
    NOT_FOUND_MESSAGE,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """
    Рабочее место с записью в папку проекта.

        tmp_path: временная папка теста.

    Возвращает: Рабочее место в tmp_path.
    """
    return Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
    )


@pytest.fixture
def tools(workspace: Workspace) -> dict[str, BaseTool]:
    """
    Файловые инструменты рабочего места по имени.

        workspace: рабочее место теста.

    Возвращает: Инструменты по имени.
    """
    return {tool.name: tool for tool in build_file_tools(workspace = workspace, seen_files = SeenFiles(), refusals = PathRefusals())}


def _edit(*, tools: dict[str, BaseTool], old_string: str, new_string: str) -> str:
    """
    Правит app.py.

        tools: инструменты по имени.
        old_string: фрагмент, который нужно заменить.
        new_string: текст на замену.

    Возвращает: Ответ edit.
    """
    return tools["edit"].invoke({"file_path": "app.py", "old_string": old_string, "new_string": new_string})


def test_edit_replaces_after_read(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    После read edit заменяет фрагмент и отвечает одной строкой.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\nb = 2\n")
    tools["read"].invoke({"file_path": "app.py"})

    result = _edit(tools = tools, old_string = "b = 2", new_string = "b = 20")

    assert result == "Правка применена: app.py"
    assert path.read_text() == "a = 1\nb = 20\n"


def test_edit_chain_needs_no_read(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Вторая правка идёт без перечитывания; правка после write — без чтения.
    """
    path = workspace.project_dir / "app.py"
    tools["write"].invoke({"file_path": "app.py", "content": "a = 1\nb = 2\n"})

    _edit(tools = tools, old_string = "a = 1", new_string = "a = 10")
    _edit(tools = tools, old_string = "b = 2", new_string = "b = 20")

    assert path.read_text() == "a = 10\nb = 20\n"


def test_edit_requires_read(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    edit без чтения файла отклоняется.
    """
    (workspace.project_dir / "app.py").write_text("a = 1\n")

    result = _edit(tools = tools, old_string = "a = 1", new_string = "a = 2")

    assert "нельзя писать в файлы, которые ты не читал" in result


def test_edit_rejects_file_changed_after_read(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Файл, изменённый после чтения, не правится.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\n")
    tools["read"].invoke({"file_path": "app.py"})
    path.write_text("a = 5\n")

    result = _edit(tools = tools, old_string = "a = 5", new_string = "a = 6")

    assert "изменился после твоего чтения" in result
    assert path.read_text() == "a = 5\n"


@pytest.mark.parametrize(
    ("old_string", "new_string", "message"),
    [
        ("a = 1", "a = 1", IDENTICAL_STRINGS_MESSAGE),
        ("", "a = 2", EMPTY_OLD_STRING_MESSAGE),
        ("c = 3", "c = 4", NOT_FOUND_MESSAGE),
    ],
)
def test_edit_refusals_keep_file(
    workspace: Workspace,
    tools: dict[str, BaseTool],
    old_string: str,
    new_string: str,
    message: str,
) -> None:
    """
    Совпадающие строки, пустой old_string и отсутствующий фрагмент — отказ, файл не меняется.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\n")
    tools["read"].invoke({"file_path": "app.py"})

    result = _edit(tools = tools, old_string = old_string, new_string = new_string)

    assert result.startswith("Ошибка") and message in result
    assert path.read_text() == "a = 1\n"


def test_edit_replace_all(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    replace_all заменяет все вхождения.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("x = 1\nx = 1\n")
    tools["read"].invoke({"file_path": "app.py"})

    tools["edit"].invoke({"file_path": "app.py", "old_string": "x", "new_string": "y", "replace_all": True})

    assert path.read_text() == "y = 1\ny = 1\n"


def test_edit_missing_file_and_directory(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Отсутствующий файл и папка — отказ.
    """
    (workspace.project_dir / "src").mkdir()

    missing = _edit(tools = tools, old_string = "a", new_string = "b")
    directory = tools["edit"].invoke({"file_path": "src", "old_string": "a", "new_string": "b"})

    assert "файл не найден" in missing
    assert directory == "Ошибка: src — папка"


def test_edit_outside_writable_dirs(workspace: Workspace) -> None:
    """
    edit вне папок записи отклоняется.
    """
    read_only_workspace = Workspace(
        project_dir = workspace.project_dir,
        private_dir = workspace.private_dir,
        input_dirs = (),
        readable_dirs = (workspace.project_dir,),
        writable_dirs = (workspace.private_dir,),
    )
    tools = {
        tool.name: tool
        for tool in build_file_tools(workspace = read_only_workspace, seen_files = SeenFiles(), refusals = PathRefusals())
    }
    (workspace.project_dir / "app.py").write_text("a = 1\n")

    result = _edit(tools = tools, old_string = "a = 1", new_string = "a = 2")

    assert result.startswith("Ошибка: запись в app.py запрещена")


@pytest.mark.parametrize(
    ("original", "old_string", "new_string", "expected"),
    [
        ("a\r\nb\r\n", "a\nb", "x\ny", "x\r\ny\r\n"),
        ("a\nb\n", "a\r\nb", "x\r\ny", "x\ny\n"),
    ],
)
def test_edit_keeps_file_line_endings(
    workspace: Workspace,
    tools: dict[str, BaseTool],
    original: str,
    old_string: str,
    new_string: str,
    expected: str,
) -> None:
    """
    Переводы строк файла сохраняются, какие бы ни пришли в аргументах.
    """
    path = workspace.project_dir / "app.py"
    path.write_bytes(original.encode("utf-8"))
    tools["read"].invoke({"file_path": "app.py"})

    _edit(tools = tools, old_string = old_string, new_string = new_string)

    assert path.read_bytes().decode("utf-8") == expected


def test_edit_cuts_read_summary_at_end(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Итоговая строка read в конце old_string отрезается после неудачного поиска; ответ сообщает о ней.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\nb = 2\n")
    summary = tools["read"].invoke({"file_path": "app.py"}).splitlines()[-1]

    result = _edit(tools = tools, old_string = f"b = 2\n\n{summary}", new_string = "b = 20")

    assert result == (
        "Правка применена: app.py\n"
        f"Замечание: old_string в вызове инструмента содержала лишнюю служебную строку: {summary}"
    )
    assert path.read_text() == "a = 1\nb = 20\n"


def test_edit_cuts_read_header_at_start(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Заголовок read в начале old_string отрезается после неудачного поиска.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\nb = 2\n")
    header = tools["read"].invoke({"file_path": "app.py"}).splitlines()[0]

    result = _edit(tools = tools, old_string = f"{header}\na = 1", new_string = "a = 10")

    assert result.endswith(f"лишнюю служебную строку: {header}")
    assert path.read_text() == "a = 10\nb = 2\n"


def test_edit_keeps_read_summary_in_middle(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Итоговая строка read в середине old_string не отрезается: отказ «не найден».
    """
    path = workspace.project_dir / "app.py"
    path.write_text("a = 1\nb = 2\n")
    summary = tools["read"].invoke({"file_path": "app.py"}).splitlines()[-1]

    result = _edit(tools = tools, old_string = f"a = 1\n{summary}\nb = 2", new_string = "x")

    assert NOT_FOUND_MESSAGE in result
    assert path.read_text() == "a = 1\nb = 2\n"


def test_edit_finds_summary_like_text_of_file(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Текст файла, похожий на итоговую строку read, находится обычным поиском и не отрезается.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("x\n(Конец файла, всего строк: 2)\n")
    tools["read"].invoke({"file_path": "app.py"})

    result = _edit(tools = tools, old_string = "x\n(Конец файла, всего строк: 2)", new_string = "y")

    assert result == "Правка применена: app.py"
    assert path.read_text() == "y\n"


def test_edit_not_found_shows_single_similar_place(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Отказ «не найден» показывает единственное похожее место в виде вывода read, файл не меняется.
    """
    path = workspace.project_dir / "app.py"
    content = "def first():\n    return 1\n\ndef second():\n    value = 2\n    return value\n\ndef third():\n    return 3\n"
    path.write_text(content)
    tools["read"].invoke({"file_path": "app.py"})

    result = _edit(
        tools = tools,
        old_string = "def second():\n    value = compute_everything()\n    return value",
        new_string = "x",
    )

    assert result == (
        f"Ошибка в app.py: {NOT_FOUND_MESSAGE}\n\n"
        "Похожее место в файле, строки 2-8:\n"
        "2:    return 1\n"
        "3:\n"
        "4:def second():\n"
        "5:    value = 2\n"
        "6:    return value\n"
        "7:\n"
        "8:def third():"
    )
    assert path.read_text() == content


def test_edit_not_found_without_single_place_has_no_hint(workspace: Workspace, tools: dict[str, BaseTool]) -> None:
    """
    Если похожих мест несколько, отказ «не найден» без подсказки.
    """
    path = workspace.project_dir / "app.py"
    path.write_text("x = 1\ny = 2\n\nx = 1\ny = 2\n")
    tools["read"].invoke({"file_path": "app.py"})

    result = _edit(tools = tools, old_string = "x = 1\ny = 3", new_string = "x = 5")

    assert result == f"Ошибка в app.py: {NOT_FOUND_MESSAGE}"
