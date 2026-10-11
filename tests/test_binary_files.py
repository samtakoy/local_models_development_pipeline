"""Тесты единого правила двоичного файла: read, edit, grep и содержимое папки отличают его одинаково."""

from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.files import decode_text
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import PathRefusals, SeenFiles, build_file_tools
from codeteam.core.tools.files.common_prompts import NOT_TEXT_REFUSAL

# Файл с нулевым байтом: в кодировке utf-8 он допустим, но по правилу он двоичный.
NULL_BYTE_CONTENT = b"name\0value\n"


@pytest.fixture
def seen_files() -> SeenFiles:
    """
    Файлы, которые видел вызов: общие для инструментов теста.

    Возвращает: Пустой набор виденных файлов.
    """
    return SeenFiles()


@pytest.fixture
def file_tools(tmp_path: Path, seen_files: SeenFiles) -> dict[str, BaseTool]:
    """
    Файловые инструменты на рабочем месте в папке теста.

    Возвращает: Инструменты по именам.
    """
    workspace = Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
    )

    return {tool.name: tool for tool in build_file_tools(workspace = workspace, seen_files = seen_files, refusals = PathRefusals())}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"one\ntwo\n", "one\ntwo\n"),
        ("строка".encode("utf-8"), "строка"),
        (NULL_BYTE_CONTENT, None),
        (b"\xff\xfe", None),
    ],
)
def test_decode_text(content: bytes, expected: str | None) -> None:
    """
    Текст в utf-8 переводится в строку; нулевой байт и не utf-8 дают None.
    """
    assert decode_text(content = content) == expected


def test_read_refuses_null_byte_file(tmp_path: Path, file_tools: dict[str, BaseTool]) -> None:
    """
    read отказывает в чтении файла с нулевым байтом.
    """
    (tmp_path / "data.bin").write_bytes(NULL_BYTE_CONTENT)

    answer = file_tools["read"].invoke({"file_path": "data.bin"})

    assert answer == NOT_TEXT_REFUSAL.format(shown_path = "data.bin")


def test_edit_refuses_null_byte_file(
    tmp_path: Path,
    file_tools: dict[str, BaseTool],
    seen_files: SeenFiles,
) -> None:
    """
    edit отказывает в правке файла с нулевым байтом, даже если файл отмечен как виденный.
    """
    path = tmp_path / "data.bin"
    path.write_bytes(NULL_BYTE_CONTENT)
    seen_files.remember(path = path, content = NULL_BYTE_CONTENT)

    answer = file_tools["edit"].invoke({"file_path": "data.bin", "old_string": "name", "new_string": "key"})

    assert answer == NOT_TEXT_REFUSAL.format(shown_path = "data.bin")
    assert path.read_bytes() == NULL_BYTE_CONTENT


def test_grep_skips_null_byte_file(tmp_path: Path, file_tools: dict[str, BaseTool]) -> None:
    """
    grep не ищет в файле с нулевым байтом.
    """
    (tmp_path / "data.bin").write_bytes(NULL_BYTE_CONTENT)

    answer = file_tools["grep"].invoke({"pattern": "name"})

    assert answer == "Совпадений нет"


def test_directory_shows_null_byte_file_as_binary(tmp_path: Path, file_tools: dict[str, BaseTool]) -> None:
    """
    В содержимом папки файл с нулевым байтом показан двоичным.
    """
    (tmp_path / "data.bin").write_bytes(NULL_BYTE_CONTENT)

    answer = file_tools["read"].invoke({"file_path": "."})

    assert answer.splitlines()[1:] == ["data.bin (двоичный или не UTF-8, 1 КБ)"]
