"""Тесты мягкого лимита истории: какие шаги считаются сверх него, когда он снимается после записи ответа
и когда агент переходит к фиксации работы."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from langchain_core.messages import AIMessage, ToolMessage

from codeteam.core.agent.graph import AGENT_CFG_NAME, _counts_against_soft_limit, route_after_tools
from codeteam.core.agent.node_ids import AGENT_NODE_ID, LIMIT_NOTICE_NODE_ID
from codeteam.core.tools.shell import BASH_TOOL_NAME, STOP_PROCESS_TOOL_NAME

# Мягкий и жёсткий лимиты истории в тестах.
SOFT_LIMIT = 100
HARD_LIMIT = 200

# Шагов сверх мягкого лимита до фиксации работы в тестах.
EXTRA_STEPS = 2


def _settings(*, tmp_path: Path) -> SimpleNamespace:
    """
    Собирает настройки агента с лимитами тестов.

        tmp_path: папка проекта теста.

    Возвращает: Настройки агента.
    """
    return SimpleNamespace(
        history_token_limit = SOFT_LIMIT,
        history_token_hard_limit = HARD_LIMIT,
        soft_limit_extra_steps = EXTRA_STEPS,
        project_dir = tmp_path,
        relative_private_dir = Path(".ct-work") / "tester_r1",
    )


def _messages(*, calls: list[tuple[str, dict]], input_tokens: int) -> list:
    """
    Собирает ответ модели с вызовами и результаты вызовов.

        calls: имя и аргументы каждого вызова шага.
        input_tokens: входные токены ответа модели с этими вызовами.

    Возвращает: Сообщения шага инструментов.
    """
    response = AIMessage(
        content = "",
        tool_calls = [
            {"id": f"call_{number}", "name": name, "args": args} for number, (name, args) in enumerate(calls)
        ],
        usage_metadata = {"input_tokens": input_tokens, "output_tokens": 1, "total_tokens": input_tokens + 1},
    )
    results = [
        ToolMessage(content = "готово", tool_call_id = f"call_{number}", name = name)
        for number, (name, _) in enumerate(calls)
    ]

    return [response, *results]


def _route(*, input_tokens: int, soft_limit_steps: int, tmp_path: Path) -> str:
    """
    Выбирает узел после шага команды bash.

        input_tokens: входные токены ответа модели.
        soft_limit_steps: сколько шагов уже сделано сверх мягкого лимита.
        tmp_path: папка проекта теста.

    Возвращает: Имя следующего узла.
    """
    messages = _messages(calls = [(BASH_TOOL_NAME, {"command": "ls"})], input_tokens = input_tokens)
    state = {"messages": messages, "repeated_results": 0, "soft_limit_steps": soft_limit_steps}

    return route_after_tools(state, {"configurable": {AGENT_CFG_NAME: _settings(tmp_path = tmp_path)}})


def test_stop_process_step_does_not_count(tmp_path: Path) -> None:
    """Шаг только с остановкой процессов сверх мягкого лимита не считается."""
    calls = [(STOP_PROCESS_TOOL_NAME, {"pid": "1"}), (STOP_PROCESS_TOOL_NAME, {"pid": "2"})]

    assert not _counts_against_soft_limit(
        cfg = _settings(tmp_path = tmp_path),
        messages = _messages(calls = calls, input_tokens = SOFT_LIMIT),
    )


def test_other_calls_count_only_over_soft_limit(tmp_path: Path) -> None:
    """Команда или остановка процесса вместе с командой считаются только сверх мягкого лимита."""
    bash_call = (BASH_TOOL_NAME, {"command": "uv run pytest"})
    for calls in ([bash_call], [(STOP_PROCESS_TOOL_NAME, {"pid": "1"}), bash_call]):
        assert _counts_against_soft_limit(
            cfg = _settings(tmp_path = tmp_path),
            messages = _messages(calls = calls, input_tokens = SOFT_LIMIT),
        )
        assert not _counts_against_soft_limit(
            cfg = _settings(tmp_path = tmp_path),
            messages = _messages(calls = calls, input_tokens = SOFT_LIMIT - 1),
        )


def test_extra_steps_before_limit_notice(tmp_path: Path) -> None:
    """Сверх мягкого лимита разрешено EXTRA_STEPS шагов, следующий переводит к фиксации работы."""
    assert _route(input_tokens = SOFT_LIMIT, soft_limit_steps = EXTRA_STEPS, tmp_path = tmp_path) == AGENT_NODE_ID
    assert _route(
        input_tokens = SOFT_LIMIT,
        soft_limit_steps = EXTRA_STEPS + 1,
        tmp_path = tmp_path,
    ) == LIMIT_NOTICE_NODE_ID


def test_hard_limit_stops_at_once(tmp_path: Path) -> None:
    """Жёсткий лимит переводит к фиксации работы сразу, без запаса шагов."""
    assert _route(input_tokens = HARD_LIMIT, soft_limit_steps = 0, tmp_path = tmp_path) == LIMIT_NOTICE_NODE_ID


# Пути записи ответа: файл контекста и раздел черновика личной папки тестов.
CONTEXT_FILE = (Path(".ct-work") / "tester_r1" / "context.md").as_posix()
DRAFT_FILE = (Path(".ct-work") / "tester_r1" / "draft" / "100_report.md").as_posix()


def _written(*, writes: list[tuple[str, str, str]]) -> list:
    """
    Собирает историю с записями ответа и последним шагом команды bash сверх мягкого лимита.

        writes: имя инструмента, путь и статус результата каждой записи: success или error.

    Возвращает: Сообщения истории.
    """
    history = []
    for number, (name, path, status) in enumerate(writes):
        call_id = f"write_{number}"
        call = {"id": call_id, "name": name, "args": {"file_path": path}}
        history.append(AIMessage(content = "", tool_calls = [call]))
        history.append(ToolMessage(content = "готово", tool_call_id = call_id, name = name, status = status))

    return [*history, *_messages(calls = [(BASH_TOOL_NAME, {"command": "ls"})], input_tokens = SOFT_LIMIT)]


def test_written_context_and_draft_lift_soft_limit(tmp_path: Path) -> None:
    """Записаны и файл контекста, и черновик — шаг сверх мягкого лимита не считается."""
    messages = _written(writes = [("write", DRAFT_FILE, "success"), ("edit", CONTEXT_FILE, "success")])

    assert not _counts_against_soft_limit(cfg = _settings(tmp_path = tmp_path), messages = messages)


@pytest.mark.parametrize(
    "writes",
    [
        [("write", DRAFT_FILE, "success")],
        [("edit", CONTEXT_FILE, "success")],
        [("write", DRAFT_FILE, "success"), ("write", CONTEXT_FILE, "error")],
        [("write", "src/app.py", "success"), ("write", CONTEXT_FILE, "success")],
        [("read", DRAFT_FILE, "success"), ("read", CONTEXT_FILE, "success")],
    ],
)
def test_partial_or_failed_writes_keep_soft_limit(tmp_path: Path, writes: list[tuple[str, str, str]]) -> None:
    """Только контекст или только черновик, запись с ошибкой, запись в чужое место или чтение — шаг считается."""
    assert _counts_against_soft_limit(cfg = _settings(tmp_path = tmp_path), messages = _written(writes = writes))
