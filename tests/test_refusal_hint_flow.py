"""Тесты пути подсказок к отказу в графе: подсказка только к отказу файлового инструмента по пути,
отказы и ошибки других инструментов без подсказки, подсказка считается замечанием хука,
повтор отказа по тому же пути остаётся повтором шага."""

import random
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from codeteam.core.agent.graph import AGENT_CFG_NAME, AgentState, make_tools_node
from codeteam.core.agent.statistics import DRAFT_PHASE, STEP_HOOK_REMARK_COUNTER, WORK_PHASE, AgentStatistics
from codeteam.core.agent.step_hooks import StepContext
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files import READ_TOOL_NAME, PathRefusals, SeenFiles, file_tool_builders
from codeteam.core.tools.shell import BASH_TOOL_NAME, build_disabled_bash_tool

# Личная папка агента относительно папки проекта.
RELATIVE_PRIVATE_DIR = Path(".ct-work") / "browser_checker_r1"

# Подсказки к отказу в тестах: много, чтобы случайный выбор почти никогда не повторял подсказку.
HINTS = tuple(f"подсказка-{number:02d}" for number in range(1, 11))

# Файл проекта вне папок, доступных агенту.
OUTSIDE_FILE = "src/app.py"

# Имя инструмента теста, который не работает с файлами и отвечает ошибкой.
FAILING_TOOL_NAME = "browser_click"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """
    Папка проекта с файлом src/app.py и личной папкой агента.

    Возвращает: Путь папки проекта.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / OUTSIDE_FILE).write_text("print(1)\n", encoding = "utf-8")
    (tmp_path / RELATIVE_PRIVATE_DIR).mkdir(parents = True)

    return tmp_path


def _workspace(*, project_dir: Path) -> Workspace:
    """
    Собирает рабочее место: чтение и запись только в личной папке.

        project_dir: папка проекта.

    Возвращает: Рабочее место.
    """
    private_dir = project_dir / RELATIVE_PRIVATE_DIR

    return Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        input_dirs = (),
        readable_dirs = (private_dir,),
        writable_dirs = (private_dir,),
    )


def _failing_tool() -> BaseTool:
    """
    Собирает инструмент, который не работает с файлами: на любой вызов отвечает ошибкой.

    Возвращает: Инструмент.
    """
    def browser_click(*, path: str | None = None) -> str:
        """
        Отвечает ошибкой.

            path: аргумент с именем, как у файловых инструментов.

        Возвращает: Ничего не возвращает: ошибку поднимает ToolException.
        """
        raise ToolException("элемент не найден")

    return StructuredTool.from_function(
        func = browser_click,
        name = FAILING_TOOL_NAME,
        description = FAILING_TOOL_NAME,
        handle_tool_error = True,
    )


def _hint_hook(context: StepContext) -> str | None:
    """
    Хук шага теста: к отказам по пути за шаг — одна подсказка из набора.

        context: шаг инструментов.

    Возвращает: Подсказку или None, если отказов не было.
    """
    if not context.refusals:
        return None

    return random.choice(HINTS)


def _tools(*, project_dir: Path, refusals: PathRefusals) -> list[BaseTool]:
    """
    Собирает инструменты теста: read рабочего места, заглушку bash и инструмент с ошибкой.

        project_dir: папка проекта.
        refusals: отказы по пути за шаг агента.

    Возвращает: Инструменты.
    """
    builders = file_tool_builders(
        workspace = _workspace(project_dir = project_dir),
        seen_files = SeenFiles(),
        refusals = refusals,
    )

    return [
        builders[READ_TOOL_NAME](),
        build_disabled_bash_tool(refusal = "bash недоступен"),
        _failing_tool(),
    ]


@dataclass(frozen = True)
class _StepsResult:
    """
    Итог нескольких шагов инструментов.

        texts: тексты ответа инструмента по шагам.
        counters: счётчики статистики агента.
        repeated_results: число повторов шага подряд после последнего шага.
    """

    texts: list[str]
    counters: dict[str, int]
    repeated_results: int


def _run_steps(*, project_dir: Path, phase: str, name: str, args: dict, step_count: int) -> _StepsResult:
    """
    Выполняет несколько шагов подряд в узле инструментов графа: в каждом шаге один и тот же вызов.
    Хук шага: подсказка к отказам по пути.

        project_dir: папка проекта.
        phase: фаза работы агента.
        name: имя инструмента.
        args: аргументы вызова.
        step_count: число шагов.

    Возвращает: Тексты ответов, счётчики статистики и число повторов шага подряд.
    """
    refusals = PathRefusals()
    tools = _tools(project_dir = project_dir, refusals = refusals)
    statistics = AgentStatistics(
        role_name = "browser_checker",
        journal_name = "01_browser_checker_r1",
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = [tool.name for tool in tools],
    )
    settings = SimpleNamespace(
        statistics = statistics,
        step_hooks = (_hint_hook,),
        project_dir = project_dir,
        relative_private_dir = RELATIVE_PRIVATE_DIR,
        path_refusals = refusals,
    )
    # узел инструментов langgraph работает только внутри графа
    workflow = StateGraph(AgentState)
    workflow.add_node("tools", make_tools_node(tools = tools, phase = phase))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    graph = workflow.compile()

    texts = []
    repeated_results = 0
    recent_tool_steps = []
    for step in range(step_count):
        call = AIMessage(content = "", tool_calls = [{"id": f"call_{step}", "name": name, "args": args}])
        result = graph.invoke(
            {
                "messages": [call],
                "reset_count": 0,
                "answer_notices": 0,
                "repeated_results": repeated_results,
                "recent_tool_steps": recent_tool_steps,
            },
            {"configurable": {AGENT_CFG_NAME: settings}},
        )
        tool_message = next(message for message in result["messages"] if isinstance(message, ToolMessage))
        texts.append(tool_message.text)
        repeated_results = result["repeated_results"]
        recent_tool_steps = result["recent_tool_steps"]

    return _StepsResult(
        texts = texts,
        counters = statistics.to_dict()["counters"],
        repeated_results = repeated_results,
    )


def _run_call(*, project_dir: Path, phase: str, name: str, args: dict) -> tuple[str, dict[str, int]]:
    """
    Выполняет один вызов инструмента в узле инструментов графа.

        project_dir: папка проекта.
        phase: фаза работы агента.
        name: имя инструмента.
        args: аргументы вызова.

    Возвращает: Текст ответа инструмента и счётчики статистики агента.
    """
    result = _run_steps(project_dir = project_dir, phase = phase, name = name, args = args, step_count = 1)

    return result.texts[0], result.counters


def _has_hint(*, text: str) -> bool:
    """
    Проверяет, есть ли в ответе инструмента подсказка к отказу.

        text: текст ответа инструмента.

    Возвращает: True, если в тексте есть одна из подсказок.
    """
    return any(hint in text for hint in HINTS)


def test_path_refusal_gets_hint(project_dir: Path) -> None:
    """
    Отказ чтения файла вне доступных папок — подсказка в ответе этого вызова.
    """
    text, _ = _run_call(
        project_dir = project_dir,
        phase = WORK_PHASE,
        name = READ_TOOL_NAME,
        args = {"file_path": OUTSIDE_FILE},
    )

    assert _has_hint(text = text)


def test_disabled_bash_refusal_has_no_hint(project_dir: Path) -> None:
    """
    Отказ заглушки bash в фазе черновика — без подсказки к отказу по пути.
    """
    text, _ = _run_call(project_dir = project_dir, phase = DRAFT_PHASE, name = BASH_TOOL_NAME, args = {"command": "ls"})

    assert not _has_hint(text = text)


@pytest.mark.parametrize("args", [{}, {"path": OUTSIDE_FILE}])
def test_failed_non_file_tool_has_no_hint(project_dir: Path, args: dict) -> None:
    """
    Ошибка инструмента, который не работает с файлами, — без подсказки, даже с аргументом path вне доступных папок.
    """
    text, _ = _run_call(project_dir = project_dir, phase = WORK_PHASE, name = FAILING_TOOL_NAME, args = args)

    assert not _has_hint(text = text)


def test_refusal_hint_is_counted_as_hook_remark(project_dir: Path) -> None:
    """
    Подсказка к отказу считается замечанием хука в статистике.
    """
    _, counters = _run_call(
        project_dir = project_dir,
        phase = WORK_PHASE,
        name = READ_TOOL_NAME,
        args = {"file_path": OUTSIDE_FILE},
    )

    assert counters[STEP_HOOK_REMARK_COUNTER] == 1


def test_repeated_path_refusal_is_repeated_step(project_dir: Path) -> None:
    """
    Тот же отказ по тому же пути три шага подряд — один и тот же ответ, второй и третий шаги считаются повторами.
    """
    result = _run_steps(
        project_dir = project_dir,
        phase = WORK_PHASE,
        name = READ_TOOL_NAME,
        args = {"file_path": OUTSIDE_FILE},
        step_count = 3,
    )

    assert _has_hint(text = result.texts[0])
    assert result.repeated_results == 2
