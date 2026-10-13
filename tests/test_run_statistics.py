"""Тесты отчёта статистики прогона: итоги агента, группы по ролям, время прогона, файл отчёта."""

from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from codeteam.app.run_statistics import RUN_REPORT_FILE_NAME, WarmupCost, agent_totals, load_run_statistics, max_context, \
    agent_seconds, run_report, run_seconds, speed_by_context, sum_totals, tokens_per_second, tool_error_percent, totals_by_role, \
    tool_phase_counts, unknown_tool_calls, unused_tools_by_role, warmup_cost, window_overflows, write_run_report
from codeteam.core.agent.statistics import REPEATED_RESULT_STOP_COUNTER, SERVER_ERROR_RETRY_COUNTER, \
    STATISTICS_FILE_SUFFIX, WORK_PHASE, AgentStatistics


def _write_agent(*, run_dir: Path, role_name: str, journal_name: str, input_tokens: int, tool_errors: int) -> None:
    """
    Пишет файл статистики агента: один запрос к модели и вызовы bash, часть с ошибкой.

        run_dir: папка прогона.
        role_name: роль агента.
        journal_name: имя журнала агента.
        input_tokens: входные токены запроса.
        tool_errors: сколько вызовов bash вернули ошибку; ещё один вызов успешный.
    """
    statistics = AgentStatistics(
        role_name = role_name,
        journal_name = journal_name,
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = ["bash"],
    )
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
    Итоги агентов собираются по ролям и складываются за роль и за прогон.
    """
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "05_developer_r1", input_tokens = 100, tool_errors = 1)
    _write_agent(run_dir = tmp_path, role_name = "developer_review", journal_name = "06_developer_review_r1", input_tokens = 50, tool_errors = 0)
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "07_developer_r2", input_tokens = 200, tool_errors = 2)

    run_statistics = load_run_statistics(run_dir = tmp_path)
    roles = {role: sum_totals(totals = totals) for role, totals in totals_by_role(run_statistics = run_statistics).items()}
    run_total = sum_totals(totals = [
        agent_totals(statistics = statistics, run_statistics = run_statistics) for statistics in run_statistics
    ])

    assert [statistics["journal"] for statistics in run_statistics] == ["05_developer_r1", "06_developer_review_r1", "07_developer_r2"]
    assert list(roles) == ["developer", "developer_review"]
    assert (roles["developer"].agents, roles["developer"].input_tokens) == (2, 300)
    assert (roles["developer"].tool_calls, roles["developer"].tool_errors) == (5, 3)
    assert (run_total.agents, run_total.input_tokens, run_total.server_errors) == (3, 350, 3)


def test_loop_to_draft_is_not_counted_as_limit(tmp_path: Path) -> None:
    """
    Переход в фазу черновика из-за петли считается отдельно от перехода по лимиту истории.
    """
    statistics = AgentStatistics(
        role_name = "bro_check",
        journal_name = "01_bro_check_r1",
        model_name = "model",
        reasoning_level = "low",
        context_window = 1000,
        tool_names = ["bash"],
    )
    statistics.record(event = {"limit_notice": {"messages": []}})
    statistics.count_in_phase(name = REPEATED_RESULT_STOP_COUNTER, phase = WORK_PHASE)
    statistics.write(path = tmp_path / f"01_bro_check_r1{STATISTICS_FILE_SUFFIX}")

    run_statistics = load_run_statistics(run_dir = tmp_path)
    totals = agent_totals(statistics = run_statistics[0], run_statistics = run_statistics)

    assert (totals.limit_notices, totals.loops_to_draft, totals.loops_to_reset) == (0, 1, 0)


def test_report_without_statistics(tmp_path: Path) -> None:
    """
    Папка без файлов статистики - сводка сообщает об этом, а не падает.
    """
    assert STATISTICS_FILE_SUFFIX in run_report(run_dir = tmp_path)


def test_run_seconds_from_first_start_to_last_end() -> None:
    """
    Время прогона — от старта первого агента до конца последнего, а не сумма времени агентов.
    """
    run_statistics = [
        {"started_at": "2026-10-11T10:00:00", "elapsed_seconds": 100.0},
        # помощник внутри первого агента
        {"started_at": "2026-10-11T10:00:30", "elapsed_seconds": 20.0},
        {"started_at": "2026-10-11T10:01:40", "elapsed_seconds": 60.0},
    ]

    assert run_seconds(run_statistics = run_statistics) == 160.0


def test_agent_seconds_with_helpers_inside_and_before() -> None:
    """
    Время агента — вместе с помощниками: помощник внутри агента время не меняет, помощник до агента добавляет
    своё время; чужие агенты не учитываются.
    """
    developer = {"journal": "06_developer_r1", "started_at": "2026-10-11T10:00:00", "elapsed_seconds": 100.0}
    developer_helper = {
        "journal": "06_developer_r1.bro_check_r1",
        "started_at": "2026-10-11T10:00:30",
        "elapsed_seconds": 20.0,
    }
    scenarios_helper = {
        "journal": "24_web_scenarios_tester_r1.bro_check_r1",
        "started_at": "2026-10-11T11:00:00",
        "elapsed_seconds": 300.0,
    }
    scenarios_tester = {
        "journal": "24_web_scenarios_tester_r1",
        "started_at": "2026-10-11T11:10:00",
        "elapsed_seconds": 60.0,
    }
    other_agent = {"journal": "06_developer_r10", "started_at": "2026-10-11T09:00:00", "elapsed_seconds": 10.0}
    run_statistics = [developer, developer_helper, scenarios_helper, scenarios_tester, other_agent]

    assert agent_seconds(statistics = developer, run_statistics = run_statistics) == 100.0
    assert agent_seconds(statistics = scenarios_tester, run_statistics = run_statistics) == 660.0


def test_report_file_in_run_dir(tmp_path: Path) -> None:
    """
    Отчёт пишется файлом в папку прогона и называет каждого агента.
    """
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "05_developer_r1", input_tokens = 100, tool_errors = 1)
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "07_developer_r2", input_tokens = 200, tool_errors = 0)

    report_path = write_run_report(run_dir = tmp_path)

    assert report_path == tmp_path / RUN_REPORT_FILE_NAME
    report = report_path.read_text(encoding = "utf-8")
    assert "05_developer_r1" in report and "07_developer_r2" in report


def _request(*, input_tokens: int, output_tokens: int, tokens_per_second: float | None) -> dict:
    """
    Собирает запрос к модели, как он записан в файле статистики.

        input_tokens: входные токены.
        output_tokens: выходные токены.
        tokens_per_second: скорость генерации; None — скорости нет.

    Возвращает: Запрос к модели.
    """
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "tokens_per_second": tokens_per_second}


def test_speed_by_context_buckets() -> None:
    """
    Скорость в интервале контекста — выходные токены на суммарное время генерации запросов интервала.
    """
    run_statistics = [
        {"requests": [
            _request(input_tokens = 10_000, output_tokens = 100, tokens_per_second = 50),
            _request(input_tokens = 30_000, output_tokens = 30, tokens_per_second = 10),
        ]},
        {"requests": [_request(input_tokens = 15_000, output_tokens = 50, tokens_per_second = 25)]},
    ]

    assert speed_by_context(run_statistics = run_statistics) == {0: (2, 37.5), 20_000: (1, 10.0)}


def test_max_context_is_largest_request() -> None:
    """
    Наибольший контекст агента — входные токены его самого большого запроса; без запросов — 0.
    """
    requests = [_request(input_tokens = tokens, output_tokens = 1, tokens_per_second = 1) for tokens in (500, 900, 700)]

    assert max_context(statistics = {"requests": requests}) == 900
    assert max_context(statistics = {"requests": []}) == 0


def test_speed_and_error_percent_of_agent(tmp_path: Path) -> None:
    """
    Скорость агента — выходные токены на время генерации; процент ошибок — ошибки на вызовы.
    """
    _write_agent(run_dir = tmp_path, role_name = "developer", journal_name = "05_developer_r1", input_tokens = 100, tool_errors = 1)
    run_statistics = load_run_statistics(run_dir = tmp_path)
    totals = agent_totals(statistics = run_statistics[0], run_statistics = run_statistics)

    assert tool_error_percent(totals = totals) == 50.0
    # в записанном запросе нет данных о времени генерации
    assert tokens_per_second(totals = totals) is None


def test_window_overflows_count_input_and_output() -> None:
    """
    Переполнение окна — запрос, у которого вход и выход вместе не меньше окна модели;
    без записанного окна запросы не проверяются.
    """
    requests = [
        _request(input_tokens = 900, output_tokens = 50, tokens_per_second = 1),
        _request(input_tokens = 990, output_tokens = 10, tokens_per_second = 1),
        _request(input_tokens = 995, output_tokens = 20, tokens_per_second = 1),
    ]

    assert window_overflows(statistics = {"context_window": 1000, "requests": requests}) == [1000, 1015]
    assert window_overflows(statistics = {"requests": requests}) is None


def test_tool_phase_counts_sum_agents_and_sort_by_errors() -> None:
    """
    Вызовы и ошибки инструмента складываются по фазам у всех агентов; инструменты идут по убыванию доли ошибок.
    """
    run_statistics = [
        {"tools": {
            "read": {"work": {"calls": 10, "errors": 1}, "warmup": {"calls": 3}},
            "bash": {"work": {"calls": 4, "errors": 2}},
        }},
        {"tools": {
            "read": {"draft": {"calls": 2, "errors": 2}},
            "bash": {"work": {"calls": 1}},
        }},
    ]

    counts = tool_phase_counts(run_statistics = run_statistics)

    # bash: 2 ошибки из 5 вызовов; read: 3 из 15
    assert list(counts) == ["bash", "read"]
    assert counts["read"] == {"work": (10, 1), "warmup": (3, 0), "draft": (2, 2)}
    assert counts["bash"] == {"work": (5, 2)}


def test_unknown_and_unused_tools() -> None:
    """
    Вызов инструмента, которого нет среди выданных, — несуществующий и не входит в таблицу инструментов;
    выданный инструмент, который не вызвал ни один агент роли, — неиспользуемый.
    """
    run_statistics = [
        {"role": "developer", "tool_names": ["read", "bash", "get_advice"], "tools": {
            "read": {"work": {"calls": 3}},
            "todo": {"draft": {"calls": 1, "errors": 1}},
        }},
        {"role": "developer", "tool_names": ["read", "bash", "get_advice"], "tools": {"bash": {"work": {"calls": 2}}}},
        {"role": "pm", "tool_names": ["read"], "tools": {"read": {"work": {"calls": 1}}}},
    ]

    assert list(tool_phase_counts(run_statistics = run_statistics)) == ["read", "bash"]
    assert unknown_tool_calls(run_statistics = run_statistics) == {"todo": (1, ["developer"])}
    assert unused_tools_by_role(run_statistics = run_statistics) == {"developer": ["get_advice"]}


def test_warmup_cost_of_start_and_resets() -> None:
    """
    Цена разогрева — вход первых запросов после старта и после сбросов; без отметки — только первый запрос.
    """
    marked = {"tools": {"read": {"warmup": {"calls": 4}, "work": {"calls": 9}}}, "requests": [
        {"input_tokens": 5_000, "after_warmup": True},
        {"input_tokens": 9_000, "after_warmup": False},
        {"input_tokens": 7_000, "after_warmup": True},
    ]}
    unmarked = {"tools": {}, "requests": [{"input_tokens": 5_000}, {"input_tokens": 9_000}]}

    assert warmup_cost(statistics = marked) == WarmupCost(warmups = 2, first_input = 5_000, total_input = 12_000, warmup_calls = 4)
    assert warmup_cost(statistics = unmarked) == WarmupCost(warmups = 1, first_input = 5_000, total_input = 5_000, warmup_calls = 0)
