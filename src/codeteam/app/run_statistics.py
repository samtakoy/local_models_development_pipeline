"""Отчёт по статистике прогона из файлов статистики агентов: сводка, переполнение окна модели, роли,
время и токены, контекст, инструменты, проблемы."""

import json
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from codeteam.core.agent.statistics import ANSWER_NOTICE_RESET_COUNTER, DRAFT_PHASE, HARD_LIMIT_COUNTER, \
    LIMIT_NOTICE_EVENT, REPEATED_RESULT_STOP_COUNTER, SERVER_ERROR_RETRY_COUNTER, STATISTICS_FILE_SUFFIX, \
    STEP_CHECK_REMARK_COUNTER, STEP_HOOK_REMARK_COUNTER, UNFINISHED_ANSWER_HINT_EVENT, \
    UNFINISHED_ANSWER_RETRY_COUNTER, WINDOW_FULL_RESET_COUNTER, WORK_PHASE

# Файл отчёта в папке прогона.
RUN_REPORT_FILE_NAME = "stats_report.md"

# Числа меньше этого показываются с одним знаком после запятой.
SMALL_NUMBER_LIMIT = 100

# Сколько строк в списках «самые»: самые долгие агенты, самый большой контекст.
TOP_COUNT = 5

# Ширина интервала размера контекста в таблице скорости, токены.
CONTEXT_BUCKET_TOKENS = 20_000

# Значение в таблице, когда данных нет.
NO_VALUE = "—"


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
        loops_to_draft: переходов в фазу черновика из-за петли: одинаковый результат инструментов подряд.
        loops_to_reset: пересборок истории из-за петли в фазе черновика.
        window_full_resets: сбросов истории, когда она дошла до края окна модели в фазе черновика.
        answer_notice_resets: сбросов истории, когда кончились попытки сдать работу.
        unfinished_answers: ответов без инструмента и без DONE: тихие повторы и подсказки.
        server_errors: повторов после ошибки сервера ollama.
        hook_remarks: замечаний хуков к файлам своих папок.
        check_remarks: замечаний проверок после шага.
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
    check_remarks: int
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
    "check_remarks": "проверки",
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
    "check_remarks",
    "failed",
)

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


def agent_totals(*, statistics: dict[str, Any]) -> RunTotals:
    """
    Считает итоги одного агента.

        statistics: статистика агента из файла.

    Возвращает: Итоги агента.
    """
    tool_phases = [phases for phases in statistics["tools"].values()]
    events = statistics["events"]
    counters = statistics["counters"]
    # в файлах, записанных до появления счётчиков по фазам, их нет
    loop_stops = statistics.get("phase_counters", {}).get(REPEATED_RESULT_STOP_COUNTER, {})
    loops_to_draft = loop_stops.get(WORK_PHASE, 0)
    unfinished_answers = events.get(UNFINISHED_ANSWER_HINT_EVENT, 0) + counters.get(UNFINISHED_ANSWER_RETRY_COUNTER, 0)

    return RunTotals(
        agents = 1,
        seconds = round(statistics["elapsed_seconds"]),
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
        loops_to_reset = loop_stops.get(DRAFT_PHASE, 0),
        window_full_resets = counters.get(WINDOW_FULL_RESET_COUNTER, 0),
        answer_notice_resets = counters.get(ANSWER_NOTICE_RESET_COUNTER, 0),
        unfinished_answers = unfinished_answers,
        server_errors = counters.get(SERVER_ERROR_RETRY_COUNTER, 0),
        hook_remarks = counters.get(STEP_HOOK_REMARK_COUNTER, 0),
        check_remarks = counters.get(STEP_CHECK_REMARK_COUNTER, 0),
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
        by_role.setdefault(statistics["role"], []).append(agent_totals(statistics = statistics))

    return by_role


def run_seconds(*, run_statistics: list[dict[str, Any]]) -> float:
    """
    Считает время прогона: от старта первого агента до конца последнего.

        run_statistics: статистика агентов прогона.

    Возвращает: Время прогона, секунды.
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

    agents = {statistics["journal"]: [agent_totals(statistics = statistics)] for statistics in run_statistics}
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
        "## Инструменты",
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


def _roles_table(*, run_statistics: list[dict[str, Any]]) -> str:
    """
    Оформляет таблицу ролей: модель, уровень размышления и число агентов роли.

        run_statistics: статистика агентов прогона.

    Возвращает: Таблицу markdown.
    """
    by_role: dict[str, list[dict[str, Any]]] = {}
    for statistics in run_statistics:
        by_role.setdefault(statistics["role"], []).append(statistics)

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
