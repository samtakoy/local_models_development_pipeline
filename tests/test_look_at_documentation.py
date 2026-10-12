"""Тесты инструмента look_at_documentation: падение советника не прерывает спросившего."""

from pathlib import Path

import pytest
from langgraph.errors import GraphRecursionError

from codeteam.common.shell import ShellProcesses
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.advisor import build_look_at_documentation_tool
from codeteam.core.roles.advisor import tool as tool_module
from codeteam.core.roles.common import CallerContext


def test_advisor_failure_returns_error_to_caller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Советник упал - спросивший получает ошибку ответом инструмента, а не исключение.
    """
    def failing_run_role(**arguments) -> Path:
        """Падает, как советник, исчерпавший предел шагов графа."""
        raise GraphRecursionError("предел шагов")

    monkeypatch.setattr(tool_module, "run_role", failing_run_role)
    caller_context = CallerContext(
        cfg = PipelineConfig(
            project_path = str(tmp_path),
            run_dir = tmp_path / "run",
            model_name = "model",
            roles = (),
            browser_check = False,
            settings = None,
        ),
        caller_name = "developer",
        caller_private_dir_name = Path("s10/developer_r1"),
        caller_journal_name = "05_s10_developer_r1",
        shell_processes = ShellProcesses(),
    )

    answer = build_look_at_documentation_tool(caller_context).invoke({"question": "почему падает тест?"})

    assert "GraphRecursionError" in answer
