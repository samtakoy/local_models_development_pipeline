"""Тесты замечаний на повтор шага инструментов: лестница замечаний, переход к записи ответа, петля из нескольких
чередующихся вызовов и разные вызовы с одинаковым ответом."""

import itertools
from pathlib import Path

import pytest
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from codeteam.core.agent import graph as graph_module
from codeteam.core.agent.graph import AGENT_CFG_NAME, REPEATED_RESULTS_LIMIT, AgentState, make_tools_node, \
    route_after_draft, route_after_tools
from codeteam.core.agent.node_ids import DRAFT_TOOL_NODE_ID, LIMIT_NOTICE_NODE_ID, REINIT_NODE_ID
from codeteam.core.agent.statistics import DRAFT_PHASE, WORK_PHASE, AgentStatistics

# Ответ инструмента, который не меняется от вызова к вызову.
SAME_RESULT = "Error: unexpected token"


def _run_steps(*, tool_func, targets: list[str], phase: str, tmp_path: Path) -> tuple[list[dict], AgentStatistics, dict]:
    """
    Выполняет шаги узла инструментов подряд: каждый шаг — вызов инструмента со своим аргументом target.

        tool_func: тело инструмента: получает target, возвращает ответ.
        targets: аргумент target каждого шага по порядку.
        phase: фаза работы агента, в которой работает узел.
        tmp_path: папка проекта теста.

    Возвращает: Состояния после каждого шага, статистику агента и конфигурацию запуска.
    """
    statistics = AgentStatistics(
        role_name = "bro_check",
        journal_name = "01_bro_check_r1",
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = ["bash"],
    )
    config = {"configurable": {AGENT_CFG_NAME: SimpleNamespace(
        statistics = statistics,
        step_hooks = (),
        project_dir = tmp_path,
        relative_private_dir = Path(".ct-work") / "bro_check_r1",
    )}}
    tool = StructuredTool.from_function(func = tool_func, name = "browser_click", description = "нажать")
    # узел инструментов langgraph работает только внутри графа
    workflow = StateGraph(AgentState)
    workflow.add_node("tools", make_tools_node(tools = [tool], phase = phase))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    graph = workflow.compile()

    state = {"messages": [], "reset_count": 0, "answer_notices": 0, "repeated_results": 0, "recent_tool_steps": []}
    states = []
    for step, target in enumerate(targets):
        call = AIMessage(content = "", tool_calls = [{"id": f"call_{step}", "name": "browser_click", "args": {"target": target}}])
        state = graph.invoke({**state, "messages": [*state["messages"], call]}, config)
        states.append(state)

    return states, statistics, config


def test_same_result_gets_ladder_of_remarks_and_stops(tmp_path: Path) -> None:
    """
    Одинаковый результат подряд: первый без замечания, дальше разные замечания по лестнице, на шестом —
    переход к записи ответа.
    """
    states, statistics, config = _run_steps(
        tool_func = lambda target: SAME_RESULT,
        targets = ["e13"] * (REPEATED_RESULTS_LIMIT + 1),
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )
    results = [state["messages"][-1].text for state in states]

    assert [state["repeated_results"] for state in states] == list(range(REPEATED_RESULTS_LIMIT + 1))
    assert results[0] == SAME_RESULT
    assert all(result.startswith(SAME_RESULT) and result != SAME_RESULT for result in results[1:])
    assert len(set(results[1:])) == len(results) - 1
    assert route_after_tools(states[-1], config) == LIMIT_NOTICE_NODE_ID
    assert statistics.to_dict()["phase_counters"] == {
        "repeated_result_remarks": {WORK_PHASE: REPEATED_RESULTS_LIMIT - 1},
        "repeated_result_stops": {WORK_PHASE: 1},
    }


@pytest.mark.parametrize("phase", [WORK_PHASE, DRAFT_PHASE])
def test_loop_counters_by_phase(tmp_path: Path, phase: str) -> None:
    """
    Счётчики петли пишутся в фазу узла инструментов.
    """
    _, statistics, _ = _run_steps(
        tool_func = lambda target: SAME_RESULT,
        targets = ["e13"] * (REPEATED_RESULTS_LIMIT + 1),
        phase = phase,
        tmp_path = tmp_path,
    )

    assert statistics.to_dict()["phase_counters"]["repeated_result_stops"] == {phase: 1}


def test_changing_result_gets_no_remarks(tmp_path: Path) -> None:
    """
    Результат меняется от шага к шагу — замечаний нет, счёт повторов не растёт.
    """
    numbers = itertools.count()
    states, statistics, _ = _run_steps(
        tool_func = lambda target: f"шаг {next(numbers)}",
        targets = ["e13"] * 4,
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [state["repeated_results"] for state in states] == [0, 0, 0, 0]
    assert [state["messages"][-1].text for state in states] == ["шаг 0", "шаг 1", "шаг 2", "шаг 3"]
    assert statistics.to_dict()["phase_counters"] == {}


def test_alternating_calls_are_repeats_within_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Окно в два шага: петля из двух чередующихся вызовов с теми же ответами считается повтором с третьего шага.
    """
    monkeypatch.setattr(graph_module, "REPEAT_WINDOW", 2)

    states, _, _ = _run_steps(
        tool_func = lambda target: SAME_RESULT,
        targets = ["e13", "e15", "e13", "e15", "e13"],
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [state["repeated_results"] for state in states] == [0, 0, 1, 2, 3]


def test_different_calls_with_same_answer_are_not_repeats(tmp_path: Path) -> None:
    """
    Разные вызовы с одинаковым ответом, как правки разных мест одного файла, — не повтор.
    """
    states, statistics, _ = _run_steps(
        tool_func = lambda target: "Правка применена: src/app.py",
        targets = ["правка 1", "правка 2", "правка 3", "правка 4"],
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [state["repeated_results"] for state in states] == [0, 0, 0, 0]
    assert statistics.to_dict()["phase_counters"] == {}


def test_loop_in_draft_ends_draft_phase() -> None:
    """
    В фазе черновика после REPEATED_RESULTS_LIMIT одинаковых результатов подряд инструменты больше не выполняются:
    работа переходит к пересборке истории; до предела вызовы выполняются.
    """
    config = {"configurable": {AGENT_CFG_NAME: SimpleNamespace(context_window_limit = 100000, max_resets = 3)}}
    call = AIMessage(content = "", tool_calls = [{"id": "call", "name": "browser_click", "args": {}}])

    def state(*, repeated_results: int) -> dict:
        """Состояние после ответа агента в фазе черновика с вызовом инструмента."""
        return {"messages": [call], "reset_count": 0, "answer_notices": 0, "repeated_results": repeated_results,
                "recent_tool_steps": []}

    assert route_after_draft(state(repeated_results = REPEATED_RESULTS_LIMIT - 1), config) == DRAFT_TOOL_NODE_ID
    assert route_after_draft(state(repeated_results = REPEATED_RESULTS_LIMIT), config) == REINIT_NODE_ID
