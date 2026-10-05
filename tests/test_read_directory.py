"""Тесты содержимого папки в инструменте read: число строк у текстовых файлов, размер у остальных."""

from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.files import FileKind, FileStats, file_stats
from codeteam.common.files.text_lines import FILE_STATS_READ_LIMIT_BYTES
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import READ_TOOL_NAME, SeenFiles, build_file_tools


@pytest.fixture
def read_tool(tmp_path: Path) -> BaseTool:
    """
    Инструмент read на рабочем месте в папке теста.

    Возвращает: Инструмент read.
    """
    workspace = Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
        refusal_hint = None,
    )
    tools = build_file_tools(workspace = workspace, seen_files = SeenFiles())

    return next(tool for tool in tools if tool.name == READ_TOOL_NAME)


def test_file_stats_text(tmp_path: Path) -> None:
    """
    Текстовый файл: вид TEXT и число строк, перевод строки в конце лишней строки не даёт.
    """
    path = tmp_path / "notes.txt"
    path.write_text("один\nдва\nтри\n", encoding = "utf-8")

    assert file_stats(path = path) == FileStats(kind = FileKind.TEXT, size_bytes = path.stat().st_size, line_count = 3)


def test_file_stats_binary(tmp_path: Path) -> None:
    """
    Файл не в utf-8: вид BINARY и размер без числа строк.
    """
    path = tmp_path / "logo.png"
    path.write_bytes(b"\x89PNG\xff\xfe" * 100)

    assert file_stats(path = path) == FileStats(kind = FileKind.BINARY, size_bytes = 600, line_count = None)


def test_file_stats_large(tmp_path: Path) -> None:
    """
    Файл больше предела: вид LARGE и размер без числа строк.
    """
    path = tmp_path / "big.log"
    path.write_bytes(b"x" * (FILE_STATS_READ_LIMIT_BYTES + 1))

    assert file_stats(path = path) == FileStats(
        kind = FileKind.LARGE,
        size_bytes = FILE_STATS_READ_LIMIT_BYTES + 1,
        line_count = None,
    )


def test_file_stats_not_regular_file(tmp_path: Path) -> None:
    """
    Для папки сведений нет.
    """
    assert file_stats(path = tmp_path) is None


def test_read_directory_shows_stats(tmp_path: Path, read_tool: BaseTool) -> None:
    """
    Содержимое папки: папка с косой чертой, у текстового файла строки, у двоичного и большого размер.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "notes.txt").write_text("один\nдва\n", encoding = "utf-8")
    (tmp_path / "logo.png").write_bytes(b"\xff" * 2000)
    (tmp_path / "big.log").write_bytes(b"x" * (3 * 1024 * 1024 + 300 * 1024))

    answer = read_tool.invoke({"file_path": "."})

    assert answer.splitlines()[1:] == [
        "big.log (большой, 3.3 МБ)",
        "logo.png (двоичный или не UTF-8, 2 КБ)",
        "notes.txt (строк: 2)",
        "src/",
    ]


def test_read_directory_hides_closed_file(tmp_path: Path, read_tool: BaseTool) -> None:
    """
    Закрытый файл .env в содержимом папки не показывается.
    """
    (tmp_path / ".env").write_text("SECRET=1\n", encoding = "utf-8")
    (tmp_path / "notes.txt").write_text("один\n", encoding = "utf-8")

    answer = read_tool.invoke({"file_path": "."})

    assert answer.splitlines()[1:] == ["notes.txt (строк: 1)"]
