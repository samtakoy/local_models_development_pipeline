"""Сводка статистики прогона: по каждому агенту, по роли и за прогон, из файлов статистики агентов."""

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from codeteam.core.agent.statistics import DRAFT_PHASE, LIMIT_NOTICE_EVENT, RESET_EVENT, SERVER_ERROR_RETRY_COUNTER, \
    STATISTICS_FILE_SUFFIX, STEP_CHECK_REMARK_COUNTER, STEP_HOOK_REMARK_COUNTER, UNFINISHED_ANSWER_HINT_EVENT, \
    UNFINISHED_ANSWER_RETRY_COUNTER


@dataclass(frozen = True)
class RunTotals:
    """
    Итоги одного агента или суммы агентов.

        agents: агентов.
        seconds: время работы, секунды.
        model_requests: запросов к модели.
        input_tokens: входных токенов.
        output_tokens: выходных токенов.
        tool_calls: вызовов инструментов.
        tool_errors: ошибок инструментов.
        draft_tool_errors: ошибок инструментов в фазе черновика.
        limit_notices: замечаний о лимите.
        resets: сбросов истории.
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
    tool_calls: int
    tool_errors: int
    draft_tool_errors: int
    limit_notices: int
    resets: int
    unfinished_answers: int
    server_errors: int
    hook_remarks: int
    check_remarks: int
    failed: int


# Заголовки столбцов сводки по полям RunTotals.
COLUMN_TITLES = {
    "agents": "агентов",
    "seconds": "время, с",
    "model_requests": "запросов",
    "input_tokens": "токены вход",
    "output_tokens": "токены выход",
    "tool_calls": "вызовов",
    "tool_errors": "ошибок вызовов",
    "draft_tool_errors": "из них в черновике",
    "limit_notices": "лимит",
    "resets": "сбросов",
    "unfinished_answers": "без инструмента",
    "server_errors": "ошибок ollama",
    "hook_remarks": "хуки",
    "check_remarks": "проверки",
    "failed": "упал",
}


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

    return RunTotals(
        agents = 1,
        seconds = statistics["elapsed_seconds"],
        model_requests = statistics["model_requests"]["count"],
        input_tokens = statistics["model_requests"]["input_tokens"],
        output_tokens = statistics["model_requests"]["output_tokens"],
        tool_calls = sum(counts.get("calls", 0) for phases in tool_phases for counts in phases.values()),
        tool_errors = sum(counts.get("errors", 0) for phases in tool_phases for counts in phases.values()),
        draft_tool_errors = sum(phases.get(DRAFT_PHASE, {}).get("errors", 0) for phases in tool_phases),
        limit_notices = events.get(LIMIT_NOTICE_EVENT, 0),
        resets = events.get(RESET_EVENT, 0),
        unfinished_answers = events.get(UNFINISHED_ANSWER_HINT_EVENT, 0) + counters.get(UNFINISHED_ANSWER_RETRY_COUNTER, 0),
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


def role_totals(*, run_statistics: list[dict[str, Any]]) -> dict[str, RunTotals]:
    """
    Складывает итоги агентов по ролям.

        run_statistics: статистика агентов прогона.

    Возвращает: Итоги по имени роли, в порядке первого появления роли в прогоне.
    """
    by_role: dict[str, list[RunTotals]] = {}
    for statistics in run_statistics:
        by_role.setdefault(statistics["role"], []).append(agent_totals(statistics = statistics))

    return {role: sum_totals(totals = totals) for role, totals in by_role.items()}


def format_table(*, rows: dict[str, RunTotals]) -> str:
    """
    Оформляет итоги таблицей: строка на каждую запись, столбец на каждое поле RunTotals.

        rows: итоги по имени строки.

    Возвращает: Таблицу текстом.
    """
    header = ["", *COLUMN_TITLES.values()]
    lines = [header]
    for name, total in rows.items():
        values = [getattr(total, field.name) for field in fields(RunTotals)]
        lines.append([name, *(f"{value:.0f}" if isinstance(value, float) else str(value) for value in values)])

    widths = [max(len(line[column]) for line in lines) for column in range(len(header))]

    return "\n".join(
        "  ".join(cell.ljust(width) if column == 0 else cell.rjust(width) for column, (cell, width) in enumerate(zip(line, widths)))
        for line in lines
    )


def run_report(*, run_dir: Path) -> str:
    """
    Собирает сводку прогона: по агентам, по ролям и за прогон.

        run_dir: папка прогона.

    Возвращает: Текст сводки; сообщение, если файлов статистики в папке нет.
    """
    run_statistics = load_run_statistics(run_dir = run_dir)
    if not run_statistics:
        return f"В {run_dir} нет файлов статистики *{STATISTICS_FILE_SUFFIX}"

    agents = {statistics["journal"]: agent_totals(statistics = statistics) for statistics in run_statistics}
    roles = role_totals(run_statistics = run_statistics)
    total = {"прогон": sum_totals(totals = list(agents.values()))}

    return "\n\n".join([
        "По агентам\n" + format_table(rows = agents),
        "По ролям\n" + format_table(rows = roles),
        "За прогон\n" + format_table(rows = total),
    ])
