"""Тесты пути хуков в графе: изменения шага инструментов → замечания хуков файлов и проверки проекта
в ответе последнего вызова шага."""

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from codeteam.common.git import UNTRACKED_STATUS, commit_all, init_repository, list_uncommitted_changes
from codeteam.core.agent.graph import AGENT_CFG_NAME, AgentState, make_tools_node
from codeteam.core.agent.statistics import WORK_PHASE, AgentStatistics
from codeteam.core.agent.step_hooks import StepContext, join_remarks
from codeteam.core.roles.common import tracked_changes_check

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "developer_r1"

# Результат каждого инструмента теста.
TOOL_RESULT = "готово"

# Замечание хука файла теста: к нему дописывается имя изменённого файла.
FILE_REMARK = "Замечание к файлу"

# Замечание проверки проекта теста.
PROJECT_REMARK = "Откатаны файлы: {paths}"

# Содержимое отслеживаемого файла проекта в коммите.
COMMITTED_CONTENT = "def view():\n    return 1\n"


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с коммитом: src/app.py.

    Возвращает: Путь папки проекта.
    """
    for name, value in {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(name, value)

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(COMMITTED_CONTENT, encoding = "utf-8")
    init_repository(project_dir = tmp_path)
    commit_all(project_dir = tmp_path, message = "init")

    return tmp_path


def _tool(*, name: str, action: Callable[[], None]) -> BaseTool:
    """
    Собирает инструмент теста: выполняет действие и возвращает TOOL_RESULT.

        name: имя инструмента.
        action: действие инструмента.

    Возвращает: Инструмент.
    """
    def run() -> str:
        """Выполняет действие."""
        action()

        return TOOL_RESULT

    return StructuredTool.from_function(func = run, name = name, description = name)


def _write_private_file_tool(*, project_dir: Path) -> BaseTool:
    """
    Собирает инструмент, который пишет файл в черновик личной папки.

        project_dir: папка проекта.

    Возвращает: Инструмент.
    """
    def action() -> None:
        """Пишет файл черновика."""
        draft_file = project_dir / RELATIVE_PRIVATE_DIR / "draft" / "100_notes.md"
        draft_file.parent.mkdir(parents = True, exist_ok = True)
        draft_file.write_text("# Заметки\n", encoding = "utf-8")

    return _tool(name = "write_private", action = action)


def _change_project_tool(*, project_dir: Path) -> BaseTool:
    """
    Собирает инструмент, который меняет отслеживаемый файл проекта.

        project_dir: папка проекта.

    Возвращает: Инструмент.
    """
    def action() -> None:
        """Меняет файл проекта."""
        (project_dir / "src" / "app.py").write_text("def view():\n    return 2\n", encoding = "utf-8")

    return _tool(name = "change_project", action = action)


def _noop_tool() -> BaseTool:
    """
    Собирает инструмент, который ничего не меняет.

    Возвращает: Инструмент.
    """
    return _tool(name = "noop", action = lambda: None)


def _file_hook(context: StepContext) -> str | None:
    """
    Хук шага теста: замечание к каждому изменённому файлу личной папки.

        context: шаг инструментов.

    Возвращает: Замечания с именами файлов или None.
    """
    return join_remarks(remarks = [f"{FILE_REMARK} {path.name}" for path in context.changed_files])


def _run_step(*, project_dir: Path, tools: list[BaseTool]) -> list[ToolMessage]:
    """
    Выполняет один шаг инструментов в узле графа: все инструменты вызываются одним ответом модели по порядку.
    Хуки шага: хук файлов всей личной папки и проверка проекта.

        project_dir: папка проекта.
        tools: инструменты шага.

    Возвращает: Ответы инструментов по порядку вызовов.
    """
    statistics = AgentStatistics(
        role_name = "developer",
        journal_name = "05_developer_r1",
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = [tool.name for tool in tools],
    )
    settings = SimpleNamespace(
        statistics = statistics,
        step_hooks = (_file_hook, tracked_changes_check(remark = PROJECT_REMARK)),
        project_dir = project_dir,
        relative_private_dir = RELATIVE_PRIVATE_DIR,
    )
    # узел инструментов langgraph работает только внутри графа
    workflow = StateGraph(AgentState)
    workflow.add_node("tools", make_tools_node(tools = tools, phase = WORK_PHASE))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    call = AIMessage(
        content = "",
        tool_calls = [{"id": f"call_{index}", "name": tool.name, "args": {}} for index, tool in enumerate(tools)],
    )

    result = workflow.compile().invoke(
        {"messages": [call], "reset_count": 0, "answer_notices": 0, "repeated_results": 0, "recent_tool_steps": []},
        {"configurable": {AGENT_CFG_NAME: settings}},
    )

    return [message for message in result["messages"] if isinstance(message, ToolMessage)]


def test_private_file_remark_goes_to_last_call(project_dir: Path) -> None:
    """
    Файл личной папки, записанный первым вызовом шага, даёт замечание в ответе последнего вызова;
    ответ первого вызова без замечаний.
    """
    messages = _run_step(
        project_dir = project_dir,
        tools = [_write_private_file_tool(project_dir = project_dir), _noop_tool()],
    )

    assert messages[0].text == TOOL_RESULT
    assert messages[-1].text.startswith(TOOL_RESULT)
    assert f"{FILE_REMARK} 100_notes.md" in messages[-1].text


def test_project_remark_follows_file_remarks(project_dir: Path) -> None:
    """
    Правка проекта откатывается, её замечание идёт после замечания к файлу личной папки.
    """
    messages = _run_step(
        project_dir = project_dir,
        tools = [_write_private_file_tool(project_dir = project_dir), _change_project_tool(project_dir = project_dir)],
    )

    last_text = messages[-1].text
    file_remark_position = last_text.index(f"{FILE_REMARK} 100_notes.md")
    project_remark_position = last_text.index("src/app.py")
    assert file_remark_position < project_remark_position
    assert (project_dir / "src" / "app.py").read_text(encoding = "utf-8") == COMMITTED_CONTENT
    changes = list_uncommitted_changes(project_dir = project_dir)
    assert [path for status, path in changes if status != UNTRACKED_STATUS] == []


def test_step_without_changes_has_no_remarks(project_dir: Path) -> None:
    """
    Шаг без изменений личной папки и проекта — ответы без замечаний.
    """
    messages = _run_step(project_dir = project_dir, tools = [_noop_tool()])

    assert [message.text for message in messages] == [TOOL_RESULT]
