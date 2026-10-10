"""Тесты статистики агента: шаги по узлам, запросы к модели, инструменты по фазам, фаза черновика, файл."""

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from codeteam.core.agent.statistics import AgentStatistics

# Длительности ответа модели в наносекундах: весь ответ и вывод токенов.
TOTAL_DURATION = 2_000_000_000
EVAL_DURATION = 1_000_000_000


def _model_answer(*, tool_names: list[str], input_tokens: int, output_tokens: int) -> AIMessage:
    """
    Собирает ответ модели с токенами и длительностями ollama.

        tool_names: инструменты, которые вызывает ответ.
        input_tokens: входные токены.
        output_tokens: выходные токены.

    Возвращает: Ответ модели.
    """
    return AIMessage(
        content = "",
        tool_calls = [{"id": f"call_{index}", "name": name, "args": {}} for index, name in enumerate(tool_names)],
        usage_metadata = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": 0},
        response_metadata = {"total_duration": TOTAL_DURATION, "eval_duration": EVAL_DURATION},
    )


def _tool_result(*, name: str, is_error: bool) -> ToolMessage:
    """
    Собирает результат инструмента.

        name: имя инструмента.
        is_error: инструмент вернул ошибку.

    Возвращает: Результат инструмента.
    """
    return ToolMessage(content = "результат", name = name, tool_call_id = "call", status = "error" if is_error else "success")


def _record_run(*, statistics: AgentStatistics) -> None:
    """
    Подаёт статистике ход агента: разогрев, работа с подсказкой после ответа без инструмента,
    замечание о лимите и черновик с двумя ошибками подряд.

        statistics: статистика агента.
    """
    events = [
        {"init": {"messages": [AIMessage(content = "", tool_calls = [{"id": "warmup_1", "name": "read", "args": {}}])]}},
        {"tools": {"messages": [_tool_result(name = "read", is_error = False)]}},
        {"agent": {"messages": [_model_answer(tool_names = ["bash"], input_tokens = 1000, output_tokens = 50)]}},
        {"tools": {"messages": [_tool_result(name = "bash", is_error = True)]}},
        {"agent": {"messages": [
            HumanMessage(content = "подсказка"),
            _model_answer(tool_names = ["read"], input_tokens = 2000, output_tokens = 30),
        ]}},
        {"tools": {"messages": [_tool_result(name = "read", is_error = False)]}},
        # замечание о лимите переписывает последний результат инструмента: это не новый вызов
        {"limit_notice": {"messages": [_tool_result(name = "read", is_error = False)]}},
        {"draft_agent": {"messages": [_model_answer(tool_names = ["bash"], input_tokens = 3000, output_tokens = 20)]}},
        {"draft_tools": {"messages": [_tool_result(name = "bash", is_error = True)]}},
        {"draft_agent": {"messages": [_model_answer(tool_names = ["bash"], input_tokens = 3100, output_tokens = 20)]}},
        {"draft_tools": {"messages": [_tool_result(name = "bash", is_error = True)]}},
        {"draft_agent": {"messages": [_model_answer(tool_names = ["write"], input_tokens = 3200, output_tokens = 40)]}},
        {"draft_tools": {"messages": [_tool_result(name = "write", is_error = False)]}},
    ]
    for event in events:
        statistics.record(event = event)


def test_statistics_of_agent_run() -> None:
    """
    Шаги, запросы к модели, инструменты по фазам, события и фаза черновика считаются по событиям графа.
    """
    statistics = AgentStatistics(role_name = "developer", journal_name = "05_stage_10_developer_r1", model_name = "model")

    _record_run(statistics = statistics)
    result = statistics.to_dict()

    assert result["steps"] == {"init": 1, "tools": 3, "agent": 2, "limit_notice": 1, "draft_agent": 3, "draft_tools": 3}
    assert result["model_requests"]["count"] == 5
    assert result["model_requests"]["input_tokens"] == 12300
    assert result["model_requests"]["output_tokens"] == 160
    assert result["requests"][0]["tokens_per_second"] == 50
    assert result["tools"] == {
        "read": {"warmup": {"calls": 1}, "work": {"calls": 1}},
        "bash": {"work": {"calls": 1, "errors": 1}, "draft": {"calls": 2, "errors": 2}},
        "write": {"draft": {"calls": 1}},
    }
    assert result["events"] == {"unfinished_answer_hints": 1, "limit_notices": 1}
    assert result["draft"]["first_response_seconds"] == [2]
    assert result["draft"]["error_streak_max"] == 2


def test_counters_error_and_file(tmp_path: Path) -> None:
    """
    Явные счётчики и ошибка запуска попадают в файл JSON.
    """
    statistics = AgentStatistics(role_name = "developer", journal_name = "05_stage_10_developer_r1", model_name = "model")
    statistics.count(name = "server_error_retries")
    statistics.count(name = "server_error_retries")
    statistics.fail(error = RuntimeError("модель недоступна"))
    path = tmp_path / "run" / "05_stage_10_developer_r1.stats.json"

    statistics.write(path = path)
    saved = json.loads(path.read_text(encoding = "utf-8"))

    assert saved["counters"] == {"server_error_retries": 2}
    assert saved["error"] == "RuntimeError: модель недоступна"
    assert saved["role"] == "developer"
