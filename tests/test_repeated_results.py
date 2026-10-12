"""Тесты замечаний на повтор шага инструментов: лестница замечаний по результатам и по вызовам, переход к записи
ответа, петля из нескольких чередующихся вызовов, разные вызовы с одинаковым ответом, переход в фазу черновика после
петли."""

import itertools
from pathlib import Path

import pytest
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from codeteam.core.agent import repeat_check as repeat_check_module
from codeteam.core.agent.graph import AGENT_CFG_NAME, AgentState, limit_notice_node, make_tools_node, \
    route_after_draft, route_after_tools
from codeteam.core.agent.repeat_check import CALL_REPEAT_CHECK, INITIAL_REPEAT_STATE, RESULT_REPEAT_CHECK, \
    RepeatState, count_repeated_calls
from codeteam.core.agent.node_ids import AGENT_NODE_ID, DRAFT_TOOL_NODE_ID, LIMIT_NOTICE_NODE_ID, REINIT_NODE_ID
from codeteam.core.agent.statistics import DRAFT_PHASE, WORK_PHASE, AgentStatistics
from codeteam.core.tools.files import PathRefusals

# Ответ инструмента, который не меняется от вызова к вызову.
SAME_RESULT = "Error: unexpected token"

# Пределы проверок повторов: по результатам и по вызовам.
REPEATED_RESULTS_LIMIT = RESULT_REPEAT_CHECK.limit
REPEATED_CALLS_LIMIT = CALL_REPEAT_CHECK.limit


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
        path_refusals = PathRefusals(),
        history_token_limit = 60000,
        history_token_hard_limit = 100000,
        soft_limit_extra_steps = 100,
        context_window_limit = 100000,
        max_resets = 3,
        limit_notice = "лимит",
        shell_processes = SimpleNamespace(kill_all = lambda: None),
    )}}
    tool = StructuredTool.from_function(func = tool_func, name = "browser_click", description = "нажать")
    # узел инструментов langgraph работает только внутри графа
    workflow = StateGraph(AgentState)
    workflow.add_node("tools", make_tools_node(tools = [tool], phase = phase))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    graph = workflow.compile()

    state = {
            "messages": [], "reset_count": 0, "answer_notices": 0, "repeats": INITIAL_REPEAT_STATE,
            "soft_limit_steps": 0,
        }
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

    assert [state["repeats"].repeated_results for state in states] == list(range(REPEATED_RESULTS_LIMIT + 1))
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

    assert [state["repeats"].repeated_results for state in states] == [0, 0, 0, 0]
    assert [state["messages"][-1].text for state in states] == ["шаг 0", "шаг 1", "шаг 2", "шаг 3"]
    assert statistics.to_dict()["phase_counters"] == {}


def test_alternating_calls_are_repeats_within_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Окно в два шага: петля из двух чередующихся вызовов с теми же ответами считается повтором с третьего шага.
    """
    monkeypatch.setattr(repeat_check_module, "REPEAT_WINDOW", 2)

    states, _, _ = _run_steps(
        tool_func = lambda target: SAME_RESULT,
        targets = ["e13", "e15", "e13", "e15", "e13"],
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [state["repeats"].repeated_results for state in states] == [0, 0, 1, 2, 3]


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

    assert [state["repeats"].repeated_results for state in states] == [0, 0, 0, 0]
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
        repeats = RepeatState(repeated_results = repeated_results, recent_result_keys = ())
        return {"messages": [call], "reset_count": 0, "answer_notices": 0, "repeats": repeats, "soft_limit_steps": 0}

    assert route_after_draft(state(repeated_results = REPEATED_RESULTS_LIMIT - 1), config) == DRAFT_TOOL_NODE_ID
    assert route_after_draft(state(repeated_results = REPEATED_RESULTS_LIMIT), config) == REINIT_NODE_ID


def _counter_from(*, start: int, after: str):
    """
    Собирает тело инструмента: первые start вызовов возвращают разные ответы, дальше — один и тот же.

        start: сколько первых вызовов возвращают разные ответы.
        after: ответ после первых start вызовов.

    Возвращает: Тело инструмента.
    """
    numbers = itertools.count()

    def tool_func(target: str) -> str:
        """Возвращает ответ по номеру вызова."""
        number = next(numbers)
        return f"шаг {number}" if number < start else after

    return tool_func


def _draft_state(*, loop_state: dict, config: dict, draft_call: AIMessage) -> dict:
    """
    Переводит состояние после петли в фазу черновика: узел лимита и ответ агента-черновика с вызовом.

        loop_state: состояние после последнего шага петли.
        config: конфигурация запуска.
        draft_call: ответ агента-черновика.

    Возвращает: Состояние перед выбором узла после ответа агента-черновика.
    """
    update = limit_notice_node(loop_state, config)

    return {
        **loop_state,
        "repeats": update["repeats"],
        "messages": [*loop_state["messages"], draft_call],
    }


def test_same_call_with_changing_result_gets_call_remarks_and_stops(tmp_path: Path) -> None:
    """
    Тот же вызов с меняющимся ответом: первые повторы без замечаний, дальше разные замечания, на пределе —
    переход к записи ответа.
    """
    numbers = itertools.count()
    states, statistics, config = _run_steps(
        tool_func = lambda target: f"шаг {next(numbers)}",
        targets = ["e13"] * (REPEATED_CALLS_LIMIT + 1),
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )
    results = [state["messages"][-1].text for state in states]
    silent_steps = CALL_REPEAT_CHECK.silent_repeats + 1

    assert [count_repeated_calls(messages = state["messages"]) for state in states] == \
        list(range(REPEATED_CALLS_LIMIT + 1))
    assert [state["repeats"].repeated_results for state in states] == [0] * (REPEATED_CALLS_LIMIT + 1)
    assert results[:silent_steps] == [f"шаг {number}" for number in range(silent_steps)]
    assert all(result != f"шаг {number + silent_steps}" for number, result in enumerate(results[silent_steps:]))
    assert len({result.removeprefix(f"шаг {number}") for number, result in enumerate(results)}) == \
        len(CALL_REPEAT_CHECK.remarks) + 2
    assert route_after_tools(states[-2], config) == AGENT_NODE_ID
    assert route_after_tools(states[-1], config) == LIMIT_NOTICE_NODE_ID
    assert statistics.to_dict()["phase_counters"] == {
        "repeated_call_remarks": {WORK_PHASE: len(CALL_REPEAT_CHECK.remarks)},
        "repeated_call_stops": {WORK_PHASE: 1},
    }


def test_result_remark_comes_before_call_remark(tmp_path: Path) -> None:
    """
    На шаге одно замечание: пока повтор только по вызовам — замечание по вызовам, когда повторился и результат —
    только замечание по результатам.
    """
    states, statistics, _ = _run_steps(
        tool_func = _counter_from(start = CALL_REPEAT_CHECK.silent_repeats + 1, after = SAME_RESULT),
        targets = ["e13"] * (CALL_REPEAT_CHECK.silent_repeats + 5),
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [state["repeats"].repeated_results for state in states][-3:] == [1, 2, 3]
    assert statistics.to_dict()["phase_counters"] == {
        "repeated_call_remarks": {WORK_PHASE: 1},
        "repeated_result_remarks": {WORK_PHASE: 3},
    }


def test_call_repeats_only_after_same_previous_call(tmp_path: Path) -> None:
    """
    Повтор по вызовам — только тот же вызов, что на прошлом шаге: разные и чередующиеся вызовы — не повтор.
    """
    numbers = itertools.count()

    different_states, _, _ = _run_steps(
        tool_func = lambda target: f"шаг {next(numbers)}",
        targets = ["e1", "e2", "e3", "e4"],
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )
    alternating_states, _, _ = _run_steps(
        tool_func = lambda target: f"шаг {next(numbers)}",
        targets = ["e13", "e15", "e13", "e15", "e13"],
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )

    assert [count_repeated_calls(messages = state["messages"]) for state in different_states] == [0, 0, 0, 0]
    assert [count_repeated_calls(messages = state["messages"]) for state in alternating_states] == [0, 0, 0, 0, 0]


@pytest.mark.parametrize("same_result", [True, False])
def test_draft_after_loop_runs_new_call(tmp_path: Path, same_result: bool) -> None:
    """
    После петли в фазе работы (по результатам или по вызовам) узел лимита обнуляет повторы по результатам,
    и новый вызов агента-черновика выполняется; повтор вызова петли в черновике не выполняется.
    """
    numbers = itertools.count()
    targets_count = (REPEATED_RESULTS_LIMIT if same_result else REPEATED_CALLS_LIMIT) + 1
    states, _, config = _run_steps(
        tool_func = (lambda target: SAME_RESULT) if same_result else (lambda target: f"шаг {next(numbers)}"),
        targets = ["e13"] * targets_count,
        phase = WORK_PHASE,
        tmp_path = tmp_path,
    )
    loop_state = states[-1]
    write_call = AIMessage(content = "", tool_calls = [{"id": "draft", "name": "write", "args": {"file_path": "a.md"}}])
    loop_call = AIMessage(content = "", tool_calls = [{"id": "draft", "name": "browser_click", "args": {"target": "e13"}}])
    write_state = _draft_state(loop_state = loop_state, config = config, draft_call = write_call)

    assert route_after_tools(loop_state, config) == LIMIT_NOTICE_NODE_ID
    assert write_state["repeats"] == INITIAL_REPEAT_STATE
    assert route_after_draft(write_state, config) == DRAFT_TOOL_NODE_ID
    if not same_result:
        loop_call_state = _draft_state(loop_state = loop_state, config = config, draft_call = loop_call)
        assert route_after_draft(loop_call_state, config) == REINIT_NODE_ID
