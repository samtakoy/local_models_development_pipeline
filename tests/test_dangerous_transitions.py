"""Тесты счётчиков опасных переходов: жёсткий лимит истории, сброс при заполненном окне, сброс после отказов сдачи."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from codeteam.core.agent.graph import AGENT_CFG_NAME, ANSWER_NOTICE_LIMIT, REPEATED_RESULTS_LIMIT, \
    count_reset_reason, limit_notice_node
from codeteam.core.agent.statistics import ANSWER_NOTICE_RESET_COUNTER, HARD_LIMIT_COUNTER, \
    WINDOW_FULL_RESET_COUNTER, AgentStatistics

# Жёсткий лимит истории и край окна модели в тестах.
HARD_LIMIT = 200
WINDOW_LIMIT = 300


def _statistics() -> AgentStatistics:
    """
    Начинает статистику агента для теста.

    Возвращает: Статистику агента.
    """
    return AgentStatistics(
        role_name = "developer",
        journal_name = "05_developer_r1",
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = ["bash"],
    )


def _messages(*, input_tokens: int) -> list:
    """
    Собирает конец истории: ответ модели с вызовом и результат вызова.

        input_tokens: входные токены ответа модели.

    Возвращает: Сообщения истории.
    """
    answer = AIMessage(
        content = "",
        tool_calls = [{"id": "call", "name": "bash", "args": {}}],
        usage_metadata = {"input_tokens": input_tokens, "output_tokens": 1, "total_tokens": input_tokens + 1},
    )

    return [answer, ToolMessage(content = "вывод", tool_call_id = "call", name = "bash")]


def _hard_limit_count(*, input_tokens: int, repeated_results: int) -> int:
    """
    Запускает узел лимита и считает переходы по жёсткому лимиту.

        input_tokens: входные токены последнего ответа модели.
        repeated_results: повторов шага инструментов подряд.

    Возвращает: Значение счётчика жёсткого лимита.
    """
    statistics = _statistics()
    config = {"configurable": {AGENT_CFG_NAME: SimpleNamespace(
        statistics = statistics,
        history_token_hard_limit = HARD_LIMIT,
        limit_notice = "лимит",
        shell_processes = SimpleNamespace(kill_all = lambda: None),
    )}}
    state = {"messages": _messages(input_tokens = input_tokens), "repeated_results": repeated_results}
    limit_notice_node(state, config)

    return statistics.to_dict()["counters"].get(HARD_LIMIT_COUNTER, 0)


def _reset_counters(*, input_tokens: int, answer_notices: int) -> dict[str, int]:
    """
    Считает причину сброса истории.

        input_tokens: входные токены последнего ответа модели.
        answer_notices: отказов в приёме работы.

    Возвращает: Явные счётчики статистики после подсчёта.
    """
    statistics = _statistics()
    cfg = SimpleNamespace(statistics = statistics, context_window_limit = WINDOW_LIMIT)
    count_reset_reason(cfg = cfg, state = {"messages": _messages(input_tokens = input_tokens), "answer_notices": answer_notices})

    return statistics.to_dict()["counters"]


def test_hard_limit_is_counted() -> None:
    """
    Переход по жёсткому лимиту считается; ниже лимита и при петле — нет.
    """
    assert _hard_limit_count(input_tokens = HARD_LIMIT, repeated_results = 0) == 1
    assert _hard_limit_count(input_tokens = HARD_LIMIT - 1, repeated_results = 0) == 0
    assert _hard_limit_count(input_tokens = HARD_LIMIT, repeated_results = REPEATED_RESULTS_LIMIT) == 0


def test_reset_reasons_are_counted() -> None:
    """
    Сброс после отказов сдачи и сброс у края окна считаются отдельно; обычный сброс не считается.
    """
    assert _reset_counters(input_tokens = WINDOW_LIMIT, answer_notices = ANSWER_NOTICE_LIMIT) == {
        ANSWER_NOTICE_RESET_COUNTER: 1,
    }
    assert _reset_counters(input_tokens = WINDOW_LIMIT, answer_notices = 0) == {WINDOW_FULL_RESET_COUNTER: 1}
    assert _reset_counters(input_tokens = WINDOW_LIMIT - 1, answer_notices = 0) == {}
