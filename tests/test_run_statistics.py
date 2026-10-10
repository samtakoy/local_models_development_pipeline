"""Тесты сводки статистики прогона: итоги агента, суммы по ролям и за прогон."""

from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from codeteam.app.run_statistics import agent_totals, load_run_statistics, role_totals, run_report, sum_totals
from codeteam.core.agent.statistics import SERVER_ERROR_RETRY_COUNTER, STATISTICS_FILE_SUFFIX, AgentStatistics


def _write_agent(*, run_dir: Path, role_name: str, journal_name: str, input_tokens: int, tool_errors: int) -> None:
    """
    Пишет файл статистики агента: один запрос к модели и вызовы bash, часть с ошибкой.

        run_dir: папка прогона.
        role_name: роль агента.
        journal_name: имя журнала агента.
        input_tokens: входные токены запроса.
        tool_errors: сколько вызовов bash вернули ошибку; ещё один вызов успешный.
    """
    statistics = AgentStatistics(role_name = role_name, journal_name = journal_name, model_name = "model")
    answer = AIMessage(
        content = "",
        tool_calls = [{"id": "call", "name": "bash", "args": {}}],
        usage_metadata = {"input_tokens": input_tokens, "output_tokens": 10, "total_tokens": 0},
    )
    statistics.record(event = {"agent": {"messages": [answer]}})
    for status in ["error"] * tool_errors + ["success"]:
        result = ToolMessage(content = "вывод", name = "bash", tool_call_id = "call", status = status)
        statistics.record(event = {"tools": {"messages": [result]}})
    statistics.count(name = SERVER_ERROR_RETRY_COUNTER)
    statistics.write(path = run_dir / f"{journal_name}{STATISTICS_FILE_SUFFIX}")


def test_totals_by_agent_role_and_run(tmp_path: Path) -> None:
    """
    Итоги агентов складываются по ролям и за прогон.
    """
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "05_developer_r1", input_tokens = 100, tool_errors = 1)
    _write_agent(run_dir = tmp_path, role_name = "developer_review", journal_name = "06_developer_review_r1", input_tokens = 50, tool_errors = 0)
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "07_developer_r2", input_tokens = 200, tool_errors = 2)

    run_statistics = load_run_statistics(run_dir = tmp_path)
    roles = role_totals(run_statistics = run_statistics)
    run_total = sum_totals(totals = [agent_totals(statistics = statistics) for statistics in run_statistics])

    assert [statistics["journal"] for statistics in run_statistics] == ["05_developer_r1", "06_developer_review_r1", "07_developer_r2"]
    assert list(roles) == ["developer", "developer_review"]
    assert (roles["developer"].agents, roles["developer"].input_tokens) == (2, 300)
    assert (roles["developer"].tool_calls, roles["developer"].tool_errors) == (5, 3)
    assert (run_total.agents, run_total.input_tokens, run_total.server_errors) == (3, 350, 3)


def test_report_without_statistics(tmp_path: Path) -> None:
    """
    Папка без файлов статистики - сводка сообщает об этом, а не падает.
    """
    assert STATISTICS_FILE_SUFFIX in run_report(run_dir = tmp_path)
