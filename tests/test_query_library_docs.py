"""Тесты инструмента query_library_docs: падение советника не прерывает спросившего; выключенный советник —
инструмента нет."""

from pathlib import Path

import pytest
from langgraph.errors import GraphRecursionError

from codeteam.common.shell import ShellProcesses
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.advisor import build_query_library_docs_tool
from codeteam.core.roles.advisor import tool as tool_module
from codeteam.core.roles.common import CallerContext


def _caller_context(*, project_dir: Path, library_docs: bool) -> CallerContext:
    """
    Собирает разработчика, для которого собирается инструмент.

        project_dir: папка проекта.
        library_docs: советник по документации из файла состава.

    Возвращает: Агента, который спрашивает советника.
    """
    return CallerContext(
        cfg = PipelineConfig(
            project_path = str(project_dir),
            run_dir = project_dir / "run",
            model_name = "model",
            roles = (),
            browser_check = False,
            library_docs = library_docs,
            settings = None,
        ),
        caller_name = "developer",
        caller_private_dir_name = Path("s10/developer_r1"),
        caller_journal_name = "05_s10_developer_r1",
        shell_processes = ShellProcesses(),
    )


def test_advisor_failure_returns_error_to_caller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Советник упал - спросивший получает ошибку ответом инструмента, а не исключение.
    """
    def failing_run_role(**arguments) -> Path:
        """Падает, как советник, исчерпавший предел шагов графа."""
        raise GraphRecursionError("предел шагов")

    monkeypatch.setattr(tool_module, "run_role", failing_run_role)
    caller_context = _caller_context(project_dir = tmp_path, library_docs = True)

    answer = build_query_library_docs_tool(caller_context).invoke({"question": "почему падает тест?"})

    assert "GraphRecursionError" in answer


def test_library_docs_off_no_tool(tmp_path: Path) -> None:
    """
    Советник по документации выключен - инструмента нет.
    """
    caller_context = _caller_context(project_dir = tmp_path, library_docs = False)

    assert build_query_library_docs_tool(caller_context) is None
