"""Отчёт по статистике прогона из файлов статистики агентов: сводка, переполнение окна модели, роли,
время и токены, контекст, разогрев, инструменты, проблемы."""

import json
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from codeteam.core.agent.statistics import ANSWER_NOTICE_RESET_COUNTER, DRAFT_PHASE, HARD_LIMIT_COUNTER, \
    LIMIT_NOTICE_EVENT, REPEATED_CALL_STOP_COUNTER, REPEATED_RESULT_STOP_COUNTER, SERVER_ERROR_RETRY_COUNTER, STATISTICS_FILE_SUFFIX, \
    STEP_HOOK_REMARK_COUNTER, UNFINISHED_ANSWER_HINT_EVENT, \
    UNFINISHED_ANSWER_RETRY_COUNTER, WARMUP_PHASE, WINDOW_FULL_RESET_COUNTER, WORK_PHASE

# Файл отчёта в папке прогона.
RUN_REPORT_FILE_NAME = "stats_report.md"

# Числа меньше этого показываются с одним знаком после запятой.
SMALL_NUMBER_LIMIT = 100

# Сколько строк в списках «самые»: самые долгие агенты, самый большой контекст.
TOP_COUNT = 5

# Сколько самых дорогих по разогреву агентов показывает отчёт.
WARMUP_TOP_COUNT = 10

# Ширина интервала размера контекста в таблице скорости, токены.
CONTEXT_BUCKET_TOKENS = 20_000

# Значение в таблице, когда данных нет.
NO_VALUE = "—"

# Разделитель в имени журнала помощника: <журнал агента>.<имя помощника>.
HELPER_JOURNAL_SEPARATOR = "."


@dataclass(frozen = True)
class RunTotals:
    """
    Итоги одного агента или суммы агентов.

        agents: агентов.
        seconds: время работы, целые секунды.
        model_requests: запросов к модели.
        input_tokens: входных токенов.
        output_tokens: выходных токенов.
        generation_seconds: время генерации выходных токенов, секунды: для скорости.
        tool_calls: вызовов инструментов.
        tool_errors: ошибок инструментов.
        draft_tool_errors: ошибок инструментов в фазе черновика.
        limit_notices: переходов в фазу черновика по лимиту истории.
        hard_limit_notices: из них по жёсткому лимиту истории.
        loops_to_draft: переходов в фазу черновика из-за петли: одинаковый результат или одинаковые вызовы
            инструментов подряд.
        loops_to_reset: пересборок истории из-за петли в фазе черновика.
        window_full_resets: сбросов истории, когда она дошла до края окна модели в фазе черновика.
        answer_notice_resets: сбросов истории, когда кончились попытки сдать работу.
        unfinished_answers: ответов без инструмента и без DONE: тихие повторы и подсказки.
        server_errors: повторов после ошибки сервера ollama.
        hook_remarks: замечаний хуков шага.
        failed: агентов, прерванных ошибкой.
    """

    agents: int
    seconds: float
    model_requests: int
    input_tokens: int
    output_tokens: int
    generation_seconds: float
    tool_calls: int
    tool_errors: int
    draft_tool_errors: int
    limit_notices: int
    hard_limit_notices: int
    loops_to_draft: int
    loops_to_reset: int
    window_full_resets: int
    answer_notice_resets: int
    unfinished_answers: int
    server_errors: int
    hook_remarks: int
    failed: int


# Заголовки столбцов: поля RunTotals и вычисляемые столбцы.
COLUMN_TITLES = {
    "agents": "агентов",
    "seconds": "время, с",
    "model_requests": "запросов",
    "input_tokens": "токены вход",
    "output_tokens": "токены выход",
    "tokens_per_second": "скорость, ток/с",
    "tool_calls": "вызовов",
    "tool_errors": "ошибок вызовов",
    "tool_error_percent": "% ошибок",
    "draft_tool_errors": "из них в черновике",
    "limit_notices": "лимит",
    "hard_limit_notices": "из них жёсткий",
    "loops_to_draft": "петля → черновик",
    "loops_to_reset": "петля → сброс",
    "window_full_resets": "сброс: окно заполнено",
    "answer_notice_resets": "сброс: отказы сдачи",
    "unfinished_answers": "без инструмента",
    "server_errors": "ошибок ollama",
    "hook_remarks": "хуки",
    "failed": "упал",
}

# Столбцы разделов отчёта.
TIME_COLUMNS = ("seconds", "model_requests", "input_tokens", "output_tokens", "tokens_per_second")
TOOL_COLUMNS = ("tool_calls", "tool_errors", "tool_error_percent", "draft_tool_errors")
PROBLEM_COLUMNS = (
    "limit_notices",
    "hard_limit_notices",
    "loops_to_draft",
    "loops_to_reset",
    "window_full_resets",
    "answer_notice_resets",
    "unfinished_answers",
    "server_errors",
    "hook_remarks",
    "failed",
)

# Фазы в таблице инструментов и их заголовки.
TOOL_PHASE_TITLES = {WORK_PHASE: "работа", DRAFT_PHASE: "черновик", WARMUP_PHASE: "разогрев"}

# Свёртка значений поля по агентам строки таблицы: сумма или среднее.
Aggregate = Callable[[list[float]], float]


def load_run_statistics(*, run_dir: Path) -> list[dict[str, Any]]:
    """
    Читает файлы статистики агентов прогона по порядку имён журналов.

        run_dir: папка прогона.

    Возвращает: Статистику агентов.
    """
    paths = sorted(run_dir.glob(f"*{STATISTICS_FILE_SUFFIX}"))

    return [json.loads(path.read_text(encoding = "utf-8")) for path in paths]


def agent_totals(*, statistics: dict[str, Any], run_statistics: list[dict[str, Any]]) -> RunTotals:
    """
    Считает итоги одного агента. Время — вместе с помощниками агента, остальное — только самого агента.

        statistics: статистика агента из файла.
        run_statistics: статистика агентов прогона: в ней ищутся помощники агента.

    Возвращает: Итоги агента.
    """
    tool_phases = [phases for phases in statistics["tools"].values()]
    events = statistics["events"]
    counters = statistics["counters"]
    # в файлах, записанных до появления счётчиков по фазам, их нет
    phase_counters = statistics.get("phase_counters", {})
    loop_stops = [
        phase_counters.get(counter_name, {})
        for counter_name in (REPEATED_RESULT_STOP_COUNTER, REPEATED_CALL_STOP_COUNTER)
    ]
    loops_to_draft = sum(stops.get(WORK_PHASE, 0) for stops in loop_stops)
    unfinished_answers = events.get(UNFINISHED_ANSWER_HINT_EVENT, 0) + counters.get(UNFINISHED_ANSWER_RETRY_COUNTER, 0)

    return RunTotals(
        agents = 1,
        seconds = round(agent_seconds(statistics = statistics, run_statistics = run_statistics)),
        model_requests = statistics["model_requests"]["count"],
        input_tokens = statistics["model_requests"]["input_tokens"],
        output_tokens = statistics["model_requests"]["output_tokens"],
        generation_seconds = sum(_generation_seconds(request = request) for request in statistics["requests"]),
        tool_calls = sum(counts.get("calls", 0) for phases in tool_phases for counts in phases.values()),
        tool_errors = sum(counts.get("errors", 0) for phases in tool_phases for counts in phases.values()),
        draft_tool_errors = sum(phases.get(DRAFT_PHASE, {}).get("errors", 0) for phases in tool_phases),
        limit_notices = events.get(LIMIT_NOTICE_EVENT, 0) - loops_to_draft,
        hard_limit_notices = counters.get(HARD_LIMIT_COUNTER, 0),
        loops_to_draft = loops_to_draft,
        loops_to_reset = sum(stops.get(DRAFT_PHASE, 0) for stops in loop_stops),
        window_full_resets = counters.get(WINDOW_FULL_RESET_COUNTER, 0),
        answer_notice_resets = counters.get(ANSWER_NOTICE_RESET_COUNTER, 0),
        unfinished_answers = unfinished_answers,
        server_errors = counters.get(SERVER_ERROR_RETRY_COUNTER, 0),
        hook_remarks = counters.get(STEP_HOOK_REMARK_COUNTER, 0),
        failed = 1 if statistics["error"] else 0,
    )


def sum_totals(*, totals: list[RunTotals]) -> RunTotals:
    """
    Складывает итоги.

        totals: итоги агентов или групп.

    Возвращает: Сумму по каждому полю.
    """
    return RunTotals(**{
        field.name: sum(getattr(total, field.name) for total in totals)
        for field in fields(RunTotals)
    })


def tokens_per_second(*, totals: RunTotals) -> float | None:
    """
    Считает скорость генерации: выходные токены на секунду генерации.

        totals: итоги агента или суммы агентов.

    Возвращает: Скорость; None, если времени генерации нет.
    """
    if not totals.generation_seconds:
        return None

    return totals.output_tokens / totals.generation_seconds


def tool_error_percent(*, totals: RunTotals) -> float | None:
    """
    Считает долю ошибок инструментов в процентах.

        totals: итоги агента или суммы агентов.

    Возвращает: Процент ошибок; None, если вызовов нет.
    """
    if not totals.tool_calls:
        return None

    return 100 * totals.tool_errors / totals.tool_calls


# Вычисляемые столбцы: считаются по сумме итогов агентов строки.
DERIVED_COLUMNS: dict[str, Callable[..., float | None]] = {
    "tokens_per_second": tokens_per_second,
    "tool_error_percent": tool_error_percent,
}


def totals_by_role(*, run_statistics: list[dict[str, Any]]) -> dict[str, list[RunTotals]]:
    """
    Собирает итоги агентов по ролям.

        run_statistics: статистика агентов прогона.

    Возвращает: Итоги агентов по имени роли, в порядке первого появления роли в прогоне.
    """
    by_role: dict[str, list[RunTotals]] = {}
    for statistics in run_statistics:
        by_role.setdefault(statistics["role"], []).append(
            agent_totals(statistics = statistics, run_statistics = run_statistics)
        )

    return by_role


def run_seconds(*, run_statistics: list[dict[str, Any]]) -> float:
    """
    Считает время прогона: от старта первого агента до конца последнего.

        run_statistics: статистика агентов прогона.

    Возвращает: Время прогона, секунды.
    """
    return _span_seconds(run_statistics = run_statistics)


def agent_seconds(*, statistics: dict[str, Any], run_statistics: list[dict[str, Any]]) -> float:
    """
    Считает время агента вместе с помощниками: от старта первого из них до конца последнего. Помощник работает
    внутри агента (вызов инструмента) или до него (прохождение сценариев до оценщика).

        statistics: статистика агента.
        run_statistics: статистика агентов прогона: помощники — агенты с журналом
            <журнал агента><HELPER_JOURNAL_SEPARATOR>...

    Возвращает: Время агента, секунды.
    """
    helper_prefix = statistics["journal"] + HELPER_JOURNAL_SEPARATOR
    helpers = [helper for helper in run_statistics if helper["journal"].startswith(helper_prefix)]

    return _span_seconds(run_statistics = [statistics, *helpers])


def _span_seconds(*, run_statistics: list[dict[str, Any]]) -> float:
    """
    Считает время от старта первого агента до конца последнего.

        run_statistics: статистика агентов.

    Возвращает: Время, секунды.
    """
    starts = [datetime.fromisoformat(statistics["started_at"]) for statistics in run_statistics]
    ends = [
        start + timedelta(seconds = statistics["elapsed_seconds"])
        for start, statistics in zip(starts, run_statistics)
    ]

    return (max(ends) - min(starts)).total_seconds()


def max_context(*, statistics: dict[str, Any]) -> int:
    """
    Находит наибольший контекст агента: входные токены самого большого запроса к модели.

        statistics: статистика агента из файла.

    Возвращает: Наибольшие входные токены запроса; 0, если запросов нет.
    """
    return max((request["input_tokens"] for request in statistics["requests"]), default = 0)


def window_overflows(*, statistics: dict[str, Any]) -> list[int] | None:
    """
    Находит запросы агента, переполнившие окно модели: вход и выход вместе не меньше окна.

        statistics: статистика агента из файла.

    Возвращает: Вход и выход вместе для каждого такого запроса по порядку; None, если окно модели
        в файле не записано.
    """
    # в файлах, записанных до появления окна модели, его нет
    context_window = statistics.get("context_window")
    if context_window is None:
        return None

    request_sizes = [request["input_tokens"] + request["output_tokens"] for request in statistics["requests"]]

    return [size for size in request_sizes if size >= context_window]


def is_offered_tool(*, statistics: dict[str, Any], tool_name: str) -> bool:
    """
    Проверяет, что инструмент был выдан модели агента.

        statistics: статистика агента из файла.
        tool_name: имя вызванного инструмента.

    Возвращает: True, если инструмент в списке выданных; True и для файлов без списка: проверить нечем.
    """
    # в файлах, записанных до появления списка выданных инструментов, его нет
    tool_names = statistics.get("tool_names")

    return tool_names is None or tool_name in tool_names


def tool_phase_counts(*, run_statistics: list[dict[str, Any]]) -> dict[str, dict[str, tuple[int, int]]]:
    """
    Складывает вызовы и ошибки каждого выданного агентам инструмента по фазам; несуществующие инструменты
    не входят.

        run_statistics: статистика агентов.

    Возвращает: По имени инструмента: по фазе — вызовы и ошибки; инструменты по убыванию доли ошибок,
        при равенстве — по убыванию числа ошибок.
    """
    counts: dict[str, dict[str, tuple[int, int]]] = {}
    for statistics in run_statistics:
        for tool_name, phases in statistics["tools"].items():
            if not is_offered_tool(statistics = statistics, tool_name = tool_name):
                continue

            tool_counts = counts.setdefault(tool_name, {})
            for phase, phase_counts in phases.items():
                calls, errors = tool_counts.get(phase, (0, 0))
                tool_counts[phase] = (calls + phase_counts.get("calls", 0), errors + phase_counts.get("errors", 0))

    def order(item: tuple[str, dict[str, tuple[int, int]]]) -> tuple[float, int]:
        """Ключ сортировки: доля ошибок и число ошибок инструмента во всех фазах."""
        calls = sum(phase_calls for phase_calls, _ in item[1].values())
        errors = sum(phase_errors for _, phase_errors in item[1].values())

        return errors / calls if calls else 0.0, errors

    return dict(sorted(counts.items(), key = order, reverse = True))


def unknown_tool_calls(*, run_statistics: list[dict[str, Any]]) -> dict[str, tuple[int, list[str]]]:
    """
    Находит вызовы несуществующих инструментов: имён, которых нет среди выданных агенту.

        run_statistics: статистика агентов.

    Возвращает: По имени инструмента: число вызовов и роли, которые его вызывали, в порядке появления;
        инструменты по убыванию вызовов.
    """
    calls: dict[str, int] = {}
    roles: dict[str, list[str]] = {}
    for statistics in run_statistics:
        for tool_name, phases in statistics["tools"].items():
            if is_offered_tool(statistics = statistics, tool_name = tool_name):
                continue

            calls[tool_name] = calls.get(tool_name, 0) + sum(counts.get("calls", 0) for counts in phases.values())
            tool_roles = roles.setdefault(tool_name, [])
            if statistics["role"] not in tool_roles:
                tool_roles.append(statistics["role"])

    ordered_names = sorted(calls, key = lambda name: calls[name], reverse = True)

    return {name: (calls[name], roles[name]) for name in ordered_names}


def unused_tools_by_role(*, run_statistics: list[dict[str, Any]]) -> dict[str, list[str]]:
    """
    Находит инструменты, выданные агентам роли, которые ни один агент роли не вызвал.

        run_statistics: статистика агентов.

    Возвращает: По имени роли: невызванные инструменты в порядке выдачи; роли, у которых все инструменты
        вызывались, и роли без списка выданных инструментов не входят.
    """
    unused = {}
    for role, role_statistics in _statistics_by_role(run_statistics = run_statistics).items():
        if any("tool_names" not in statistics for statistics in role_statistics):
            continue

        offered = dict.fromkeys(name for statistics in role_statistics for name in statistics["tool_names"])
        called = {name for statistics in role_statistics for name in statistics["tools"]}
        role_unused = [name for name in offered if name not in called]
        if role_unused:
            unused[role] = role_unused

    return unused


@dataclass(frozen = True)
class WarmupCost:
    """
    Цена разогрева агента.

        warmups: разогревов: старт и каждый сброс истории.
        first_input: вход первого запроса после старта, токены.
        total_input: вход всех первых запросов после разогрева вместе, токены.
        warmup_calls: вызовов инструментов разогрева.
    """

    warmups: int
    first_input: int
    total_input: int
    warmup_calls: int


def warmup_cost(*, statistics: dict[str, Any]) -> WarmupCost:
    """
    Считает цену разогрева агента: вход первых запросов после старта и после каждого сброса истории.

        statistics: статистика агента из файла.

    Возвращает: Цену разогрева; в файлах без отметки разогрева в запросах учтён только первый запрос.
    """
    requests = statistics["requests"]
    if requests and "after_warmup" in requests[0]:
        inputs = [request["input_tokens"] for request in requests if request["after_warmup"]]
    else:
        # в файлах, записанных до появления отметки разогрева, её нет
        inputs = [request["input_tokens"] for request in requests[:1]]
    warmup_calls = sum(phases.get(WARMUP_PHASE, {}).get("calls", 0) for phases in statistics["tools"].values())

    return WarmupCost(
        warmups = len(inputs),
        first_input = inputs[0] if inputs else 0,
        total_input = sum(inputs),
        warmup_calls = warmup_calls,
    )


def speed_by_context(*, run_statistics: list[dict[str, Any]]) -> dict[int, tuple[int, float | None]]:
    """
    Считает скорость генерации по интервалам размера контекста шириной CONTEXT_BUCKET_TOKENS.

        run_statistics: статистика агентов прогона.

    Возвращает: По началу интервала, токены: число запросов и скорость генерации в интервале,
        по возрастанию интервалов.
    """
    buckets: dict[int, list[dict[str, Any]]] = {}
    for statistics in run_statistics:
        for request in statistics["requests"]:
            bucket = request["input_tokens"] // CONTEXT_BUCKET_TOKENS * CONTEXT_BUCKET_TOKENS
            buckets.setdefault(bucket, []).append(request)

    speeds = {}
    for bucket, requests in sorted(buckets.items()):
        generation = sum(_generation_seconds(request = request) for request in requests)
        output = sum(request["output_tokens"] for request in requests if request["tokens_per_second"])
        speeds[bucket] = (len(requests), output / generation if generation else None)

    return speeds


def format_table(
    *,
    rows: dict[str, list[RunTotals]],
    columns: tuple[str, ...],
    aggregate: Aggregate,
    with_agent_count: bool,
) -> str:
    """
    Оформляет таблицу markdown: строка на каждую группу агентов, столбцы полей и вычисляемых столбцов.

        rows: итоги агентов по имени строки.
        columns: поля RunTotals и вычисляемые столбцы DERIVED_COLUMNS.
        aggregate: свёртка значений поля по агентам строки; вычисляемые столбцы считаются по сумме итогов.
        with_agent_count: первым столбцом показать число агентов строки.

    Возвращает: Таблицу markdown.
    """
    count_titles = [COLUMN_TITLES["agents"]] if with_agent_count else []
    header = ["", *count_titles, *(COLUMN_TITLES[column] for column in columns)]
    lines = [_table_row(cells = header), _table_alignment(column_count = len(header))]
    for name, totals in rows.items():
        counts = [str(len(totals))] if with_agent_count else []
        values = [_column_value(totals = totals, column = column, aggregate = aggregate) for column in columns]
        lines.append(_table_row(cells = [name, *counts, *values]))

    return "\n".join(lines)


def run_report(*, run_dir: Path) -> str:
    """
    Собирает отчёт прогона markdown: сводка, роли, время и токены, контекст, инструменты, проблемы.
    Таблицы по каждому агенту свёрнуты.

        run_dir: папка прогона.

    Возвращает: Текст отчёта; сообщение, если файлов статистики в папке нет.
    """
    run_statistics = load_run_statistics(run_dir = run_dir)
    if not run_statistics:
        return f"В {run_dir} нет файлов статистики *{STATISTICS_FILE_SUFFIX}"

    agents = {
        statistics["journal"]: [agent_totals(statistics = statistics, run_statistics = run_statistics)]
        for statistics in run_statistics
    }
    roles = totals_by_role(run_statistics = run_statistics)
    all_agents = [totals[0] for totals in agents.values()]
    agents_with_problems = {
        name: totals for name, totals in agents.items()
        if any(getattr(totals[0], column) for column in PROBLEM_COLUMNS)
    }
    role_averages_and_all = {**roles, "все агенты": all_agents}
    role_sums_and_run = {**roles, "прогон": all_agents}
    sections = [
        f"# Статистика прогона {run_dir.name}",
        "## Сводка",
        _summary(run_statistics = run_statistics, agents = agents),
        "## Переполнение окна модели",
        _overflow_section(run_statistics = run_statistics),
        "## Роли",
        _roles_table(run_statistics = run_statistics),
        "## Время и токены",
        "Время агента включает время его помощников.",
        "### По ролям, среднее на агента",
        format_table(rows = role_averages_and_all, columns = TIME_COLUMNS, aggregate = mean, with_agent_count = True),
        _details(
            title = "По агентам",
            body = format_table(rows = agents, columns = TIME_COLUMNS, aggregate = sum, with_agent_count = False),
        ),
        "## Контекст",
        _context_section(run_statistics = run_statistics),
        "## Разогрев",
        _warmup_section(run_statistics = run_statistics),
        "## Инструменты",
        "### По инструментам, весь прогон",
        _tool_table(run_statistics = run_statistics),
        "### Несуществующие инструменты",
        _unknown_tools_section(run_statistics = run_statistics),
        "### Неиспользуемые инструменты",
        _unused_tools_section(run_statistics = run_statistics),
        _details(
            title = "По инструментам, по ролям",
            body = "\n\n".join(
                f"**{role}**\n\n{_tool_table(run_statistics = role_statistics)}"
                for role, role_statistics in _statistics_by_role(run_statistics = run_statistics).items()
            ),
        ),
        "### По ролям, среднее на агента",
        format_table(rows = role_averages_and_all, columns = TOOL_COLUMNS, aggregate = mean, with_agent_count = True),
        _details(
            title = "По агентам",
            body = format_table(rows = agents, columns = TOOL_COLUMNS, aggregate = sum, with_agent_count = False),
        ),
        "## Проблемы",
        "### По ролям, всего",
        format_table(rows = role_sums_and_run, columns = PROBLEM_COLUMNS, aggregate = sum, with_agent_count = True),
        _details(
            title = "По агентам, только с проблемами",
            body = format_table(
                rows = agents_with_problems,
                columns = PROBLEM_COLUMNS,
                aggregate = sum,
                with_agent_count = False,
            ),
        ),
    ]

    return "\n\n".join(sections) + "\n"


def write_run_report(*, run_dir: Path) -> Path:
    """
    Пишет отчёт прогона файлом в папку прогона.

        run_dir: папка прогона.

    Возвращает: Файл отчёта.
    """
    report_path = run_dir / RUN_REPORT_FILE_NAME
    report_path.write_text(run_report(run_dir = run_dir), encoding = "utf-8")

    return report_path


def _summary(*, run_statistics: list[dict[str, Any]], agents: dict[str, list[RunTotals]]) -> str:
    """
    Собирает сводку прогона: агенты, время, токены, вызовы, ошибки, самые долгие агенты.

        run_statistics: статистика агентов прогона.
        agents: итоги агентов по имени журнала.

    Возвращает: Сводку markdown.
    """
    total = sum_totals(totals = [totals[0] for totals in agents.values()])
    longest = sorted(agents.items(), key = lambda item: item[1][0].seconds, reverse = True)[:TOP_COUNT]
    lines = [
        f"- агентов: {total.agents}, ролей: {len({statistics['role'] for statistics in run_statistics})}, "
        f"упали: {total.failed}",
        f"- время прогона: {_duration(seconds = run_seconds(run_statistics = run_statistics))}",
        f"- токены: вход {_number(value = total.input_tokens)}, выход {_number(value = total.output_tokens)}",
        f"- запросов к модели: {_number(value = total.model_requests)}, "
        f"скорость: {_optional_number(value = tokens_per_second(totals = total))} ток/с",
        f"- вызовов инструментов: {_number(value = total.tool_calls)}, ошибок: {_number(value = total.tool_errors)} "
        f"({_optional_number(value = tool_error_percent(totals = total))} %)",
        "",
        "Самые долгие агенты:",
        "",
        *(
            f"{position}. {name} — {_duration(seconds = totals[0].seconds)}"
            for position, (name, totals) in enumerate(longest, start = 1)
        ),
    ]

    return "\n".join(lines)


def _overflow_section(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Собирает раздел переполнения окна модели: агенты, у которых вход и выход запроса вместе достигли окна.

        run_statistics: статистика агентов прогона.

    Возвращает: Раздел markdown: таблица агентов с переполнением или строка, что переполнений нет;
        отдельной строкой — сколько агентов без записанного окна модели.
    """
    overflows = {
        statistics["journal"]: (statistics, window_overflows(statistics = statistics))
        for statistics in run_statistics
    }
    unknown_count = sum(1 for _, sizes in overflows.values() if sizes is None)
    overflowed = {journal: (statistics, sizes) for journal, (statistics, sizes) in overflows.items() if sizes}
    parts = []
    if overflowed:
        lines = [
            _table_row(cells = ["", "окно модели", "запросов с переполнением", "наибольший вход и выход"]),
            _table_alignment(column_count = 4),
            *(
                _table_row(cells = [
                    journal,
                    _number(value = statistics["context_window"]),
                    _number(value = len(sizes)),
                    _number(value = max(sizes)),
                ])
                for journal, (statistics, sizes) in overflowed.items()
            ),
        ]
        parts.append("\n".join(lines))
    elif unknown_count < len(overflows):
        parts.append("Переполнений нет: ни в одном запросе вход и выход вместе не достигли окна модели.")

    if unknown_count:
        parts.append(f"Окно модели не записано в статистике {unknown_count} агентов: их запросы не проверены.")

    return "\n\n".join(parts)


def _tool_table(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Оформляет таблицу инструментов: всего вызовов, ошибок и процент ошибок, затем вызовы и ошибки по фазам.

        run_statistics: статистика агентов, чьи вызовы складываются.

    Возвращает: Таблицу markdown.
    """
    phase_titles = [f"{title}: вызовов / ошибок" for title in TOOL_PHASE_TITLES.values()]
    total_titles = [COLUMN_TITLES[column] for column in ("tool_calls", "tool_errors", "tool_error_percent")]
    header = ["", *total_titles, *phase_titles]
    lines = [_table_row(cells = header), _table_alignment(column_count = len(header))]
    for tool_name, phases in tool_phase_counts(run_statistics = run_statistics).items():
        calls = sum(phase_calls for phase_calls, _ in phases.values())
        errors = sum(phase_errors for _, phase_errors in phases.values())
        percent = 100 * errors / calls if calls else None
        phase_cells = [
            _calls_and_errors(counts = phases[phase]) if phase in phases else NO_VALUE
            for phase in TOOL_PHASE_TITLES
        ]
        lines.append(_table_row(cells = [
            tool_name,
            _number(value = calls),
            _number(value = errors),
            _optional_number(value = percent),
            *phase_cells,
        ]))

    return "\n".join(lines)


def _unknown_tools_section(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Оформляет раздел несуществующих инструментов: имена, которые модель вызвала, но которых ей не выдавали.

        run_statistics: статистика агентов прогона.

    Возвращает: Таблицу markdown или строку, что таких вызовов нет; отдельной строкой — сколько агентов
        без списка выданных инструментов.
    """
    unknown = unknown_tool_calls(run_statistics = run_statistics)
    note = _missing_tool_names_note(run_statistics = run_statistics)
    parts = []
    if unknown:
        lines = [
            _table_row(cells = ["", COLUMN_TITLES["tool_calls"], "роли"]),
            "|---|---:|---|",
            *(
                _table_row(cells = [name, _number(value = calls), ", ".join(roles)])
                for name, (calls, roles) in unknown.items()
            ),
        ]
        parts.append("\n".join(lines))
    elif _has_tool_names(run_statistics = run_statistics):
        parts.append("Вызовов несуществующих инструментов нет.")

    parts.extend(note)

    return "\n\n".join(parts)


def _unused_tools_section(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Оформляет раздел неиспользуемых инструментов: по роли — выданные инструменты, которые никто не вызвал.

        run_statistics: статистика агентов прогона.

    Возвращает: Таблицу markdown или строку, что неиспользуемых нет; отдельной строкой — сколько агентов
        без списка выданных инструментов.
    """
    unused = unused_tools_by_role(run_statistics = run_statistics)
    note = _missing_tool_names_note(run_statistics = run_statistics)
    parts = []
    if unused:
        lines = [
            _table_row(cells = ["", "ни разу не вызваны"]),
            "|---|---|",
            *(_table_row(cells = [role, ", ".join(names)]) for role, names in unused.items()),
        ]
        parts.append("\n".join(lines))
    elif _has_tool_names(run_statistics = run_statistics):
        parts.append("Все выданные инструменты вызывались.")

    parts.extend(note)

    return "\n\n".join(parts)


def _has_tool_names(*, run_statistics: list[dict[str, Any]]) -> bool:
    """
    Проверяет, что список выданных инструментов записан хотя бы у одного агента.

        run_statistics: статистика агентов прогона.

    Возвращает: True, если хотя бы у одного агента список есть.
    """
    return any("tool_names" in statistics for statistics in run_statistics)


def _missing_tool_names_note(*, run_statistics: list[dict[str, Any]]) -> list[str]:
    """
    Собирает пометку об агентах, у которых в статистике нет списка выданных инструментов.

        run_statistics: статистика агентов прогона.

    Возвращает: Пометку одной строкой в списке; пустой список, если список есть у всех агентов.
    """
    missing_count = sum(1 for statistics in run_statistics if "tool_names" not in statistics)
    if not missing_count:
        return []

    return [f"Список выданных инструментов не записан в статистике {missing_count} агентов: их вызовы не проверены."]


def _calls_and_errors(*, counts: tuple[int, int]) -> str:
    """
    Показывает вызовы и ошибки инструмента в фазе одной ячейкой.

        counts: вызовы и ошибки.

    Возвращает: Ячейку вида «12 / 3».
    """
    calls, errors = counts

    return f"{_number(value = calls)} / {_number(value = errors)}"


def _statistics_by_role(*, run_statistics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Собирает статистику агентов по ролям.

        run_statistics: статистика агентов прогона.

    Возвращает: Статистику агентов по имени роли, в порядке первого появления роли в прогоне.
    """
    by_role: dict[str, list[dict[str, Any]]] = {}
    for statistics in run_statistics:
        by_role.setdefault(statistics["role"], []).append(statistics)

    return by_role


def _roles_table(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Оформляет таблицу ролей: модель, уровень размышления и число агентов роли.

        run_statistics: статистика агентов прогона.

    Возвращает: Таблицу markdown.
    """
    by_role = _statistics_by_role(run_statistics = run_statistics)
    lines = [
        _table_row(cells = ["", "модель", "размышление", COLUMN_TITLES["agents"]]),
        "|---|---|---|---:|",
    ]
    for role, role_statistics in by_role.items():
        # в файлах, записанных до появления уровня размышления, его нет
        models = _distinct(values = [statistics["model_name"] for statistics in role_statistics])
        levels = _distinct(values = [statistics.get("reasoning_level", NO_VALUE) for statistics in role_statistics])
        lines.append(_table_row(cells = [role, models, levels, str(len(role_statistics))]))

    return "\n".join(lines)


def _context_section(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Собирает раздел контекста: самые большие контексты агентов и ролей, среднее по всем агентам,
    скорость генерации по размеру контекста.

        run_statistics: статистика агентов прогона.

    Возвращает: Раздел markdown.
    """
    contexts = {statistics["journal"]: max_context(statistics = statistics) for statistics in run_statistics}
    by_role: dict[str, list[int]] = {}
    for statistics in run_statistics:
        by_role.setdefault(statistics["role"], []).append(contexts[statistics["journal"]])
    role_means = {role: mean(values) for role, values in by_role.items()}
    largest_agents = sorted(contexts.items(), key = lambda item: item[1], reverse = True)[:TOP_COUNT]
    largest_roles = sorted(role_means.items(), key = lambda item: item[1], reverse = True)[:TOP_COUNT]
    speed_lines = [
        _table_row(cells = ["контекст, токены", "запросов", COLUMN_TITLES["tokens_per_second"]]),
        "|---|---:|---:|",
        *(
            _table_row(cells = [
                f"{_number(value = bucket)}–{_number(value = bucket + CONTEXT_BUCKET_TOKENS)}",
                _number(value = count),
                _optional_number(value = speed),
            ])
            for bucket, (count, speed) in speed_by_context(run_statistics = run_statistics).items()
        ),
    ]

    return "\n\n".join([
        "Наибольший контекст агента — входные токены его самого большого запроса. "
        f"Среднее по всем агентам: {_number(value = mean(contexts.values()))}.",
        "### Самые большие контексты агентов",
        "\n".join(
            f"{position}. {name} — {_number(value = context)}"
            for position, (name, context) in enumerate(largest_agents, start = 1)
        ),
        "### Самые большие контексты ролей, среднее на агента",
        "\n".join(
            f"{position}. {role} — {_number(value = context)}"
            for position, (role, context) in enumerate(largest_roles, start = 1)
        ),
        "### Скорость генерации по размеру контекста",
        "\n".join(speed_lines),
    ])


def _warmup_section(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Собирает раздел разогрева: самые дорогие по разогреву агенты и среднее на агента по ролям.

        run_statistics: статистика агентов прогона.

    Возвращает: Раздел markdown.
    """
    costs = {statistics["journal"]: warmup_cost(statistics = statistics) for statistics in run_statistics}
    header = ["разогревов", "вход первого запроса", "всего на разогревы", "вызовов разогрева"]
    most_expensive = sorted(costs.items(), key = lambda item: item[1].total_input, reverse = True)[:WARMUP_TOP_COUNT]
    agent_lines = [
        _table_row(cells = ["", *header]),
        _table_alignment(column_count = len(header) + 1),
        *(
            _table_row(cells = [journal, *(_number(value = value) for value in _warmup_values(cost = cost))])
            for journal, cost in most_expensive
        ),
    ]
    role_lines = [
        _table_row(cells = ["", COLUMN_TITLES["agents"], *header]),
        _table_alignment(column_count = len(header) + 2),
    ]
    for role, role_statistics in _statistics_by_role(run_statistics = run_statistics).items():
        role_costs = [costs[statistics["journal"]] for statistics in role_statistics]
        averages = [mean(values) for values in zip(*(_warmup_values(cost = cost) for cost in role_costs))]
        role_lines.append(_table_row(cells = [
            role,
            str(len(role_costs)),
            *(_number(value = value) for value in averages),
        ]))

    return "\n\n".join([
        "Цена разогрева — вход первого запроса после старта и после каждого сброса истории: системный промпт, "
        "описания инструментов и чтения разогрева. В файлах статистики без отметки разогрева учтён только "
        "первый запрос агента.",
        f"### Самые дорогие по разогреву агенты, {WARMUP_TOP_COUNT}",
        "\n".join(agent_lines),
        "### По ролям, среднее на агента",
        "\n".join(role_lines),
    ])


def _warmup_values(*, cost: WarmupCost) -> tuple[int, int, int, int]:
    """
    Раскладывает цену разогрева по столбцам таблицы.

        cost: цена разогрева агента.

    Возвращает: Разогревов, вход первого запроса, всего на разогревы, вызовов разогрева.
    """
    return cost.warmups, cost.first_input, cost.total_input, cost.warmup_calls


def _column_value(*, totals: list[RunTotals], column: str, aggregate: Aggregate) -> str:
    """
    Считает значение столбца для строки таблицы.

        totals: итоги агентов строки.
        column: поле RunTotals или вычисляемый столбец.
        aggregate: свёртка значений поля по агентам строки.

    Возвращает: Значение текстом.
    """
    derived = DERIVED_COLUMNS.get(column)
    if derived is not None:
        return _optional_number(value = derived(totals = sum_totals(totals = totals)))

    return _number(value = aggregate([getattr(total, column) for total in totals]))


def _generation_seconds(*, request: dict[str, Any]) -> float:
    """
    Находит время генерации выходных токенов запроса по его скорости.

        request: запрос к модели из файла статистики.

    Возвращает: Время генерации, секунды; 0, если скорости нет.
    """
    if not request["tokens_per_second"]:
        return 0.0

    return request["output_tokens"] / request["tokens_per_second"]


def _details(*, title: str, body: str) -> str:
    """
    Сворачивает блок markdown под заголовок, который раскрывается по нажатию.

        title: заголовок свёрнутого блока.
        body: содержимое блока.

    Возвращает: Свёрнутый блок.
    """
    return f"<details>\n<summary>{title}</summary>\n\n{body}\n\n</details>"


def _table_row(*, cells: list[str]) -> str:
    """
    Оформляет строку таблицы markdown.

        cells: ячейки строки.

    Возвращает: Строку таблицы.
    """
    return "| " + " | ".join(cells) + " |"


def _table_alignment(*, column_count: int) -> str:
    """
    Оформляет строку выравнивания таблицы markdown: первый столбец влево, остальные вправо.

        column_count: число столбцов.

    Возвращает: Строку выравнивания.
    """
    return "|" + "|".join(["---", *("---:" for _ in range(column_count - 1))]) + "|"


def _distinct(*, values: list[str]) -> str:
    """
    Перечисляет разные значения через запятую в порядке первого появления.

        values: значения.

    Возвращает: Разные значения строкой.
    """
    return ", ".join(dict.fromkeys(values))


def _number(*, value: float) -> str:
    """
    Показывает число с пробелами между разрядами: целое и от 100 и больше — без дробной части,
    меньше 100 — с одним знаком после запятой.

        value: число.

    Возвращает: Число текстом.
    """
    if float(value).is_integer() or abs(value) >= SMALL_NUMBER_LIMIT:
        return f"{value:,.0f}".replace(",", " ")

    return f"{value:,.1f}".replace(",", " ")


def _optional_number(*, value: float | None) -> str:
    """
    Показывает число или прочерк, если значения нет.

        value: число или None.

    Возвращает: Число текстом или прочерк.
    """
    return NO_VALUE if value is None else _number(value = value)


def _duration(*, seconds: float) -> str:
    """
    Показывает длительность часами, минутами и секундами.

        seconds: длительность, секунды.

    Возвращает: Длительность вида 1:02:03.
    """
    return str(timedelta(seconds = round(seconds)))
