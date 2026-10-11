"""Тесты мягкого лимита истории: какие шаги инструментов переводят агента к фиксации работы."""

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from codeteam.core.agent.graph import AGENT_CFG_NAME, route_after_tools
from codeteam.core.agent.node_ids import AGENT_NODE_ID, LIMIT_NOTICE_NODE_ID
from codeteam.core.tools.shell import BASH_TOOL_NAME, STOP_PROCESS_TOOL_NAME

# Мягкий и жёсткий лимиты истории в тестах.
SOFT_LIMIT = 100
HARD_LIMIT = 200


def _route(*, calls: list[tuple[str, dict]], input_tokens: int, tmp_path: Path) -> str:
    """
    Выбирает узел после шага инструментов с заданными вызовами.

        calls: имя и аргументы каждого вызова шага.
        input_tokens: входные токены ответа модели с этими вызовами.
        tmp_path: папка проекта теста.

    Возвращает: Имя следующего узла.
    """
    response = AIMessage(
        content = "",
        tool_calls = [{"id": f"call_{number}", "name": name, "args": args} for number, (name, args) in enumerate(calls)],
        usage_metadata = {"input_tokens": input_tokens, "output_tokens": 1, "total_tokens": input_tokens + 1},
    )
    results = [
        ToolMessage(content = "готово", tool_call_id = f"call_{number}", name = name)
        for number, (name, _) in enumerate(calls)
    ]
    state = {"messages": [response, *results], "repeated_results": 0}
    config = {"configurable": {AGENT_CFG_NAME: SimpleNamespace(
        history_token_limit = SOFT_LIMIT,
        history_token_hard_limit = HARD_LIMIT,
        project_dir = tmp_path,
        relative_private_dir = Path(".ct-work") / "tester_r1",
    )}}

    return route_after_tools(state, config)


def test_stop_process_step_ignores_soft_limit(tmp_path: Path) -> None:
    """
    Шаг только с остановкой процессов после мягкого лимита продолжает работу.
    """
    calls = [(STOP_PROCESS_TOOL_NAME, {"pid": "1"}), (STOP_PROCESS_TOOL_NAME, {"pid": "2"})]

    assert _route(calls = calls, input_tokens = SOFT_LIMIT, tmp_path = tmp_path) == AGENT_NODE_ID


def test_stop_process_step_stops_at_hard_limit(tmp_path: Path) -> None:
    """
    Шаг с остановкой процессов после жёсткого лимита переводит к фиксации работы.
    """
    calls = [(STOP_PROCESS_TOOL_NAME, {"pid": "1"})]

    assert _route(calls = calls, input_tokens = HARD_LIMIT, tmp_path = tmp_path) == LIMIT_NOTICE_NODE_ID


def test_other_calls_stop_at_soft_limit(tmp_path: Path) -> None:
    """
    Запуск команды или остановка процесса вместе с командой после мягкого лимита переводят к фиксации работы.
    """
    bash_call = (BASH_TOOL_NAME, {"command": "uv run pytest"})
    for calls in ([bash_call], [(STOP_PROCESS_TOOL_NAME, {"pid": "1"}), bash_call]):
        assert _route(calls = calls, input_tokens = SOFT_LIMIT, tmp_path = tmp_path) == LIMIT_NOTICE_NODE_ID
