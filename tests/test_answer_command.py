"""Тесты распознавания попытки сдать работу командой bash."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from codeteam.core.agent.graph import _is_answer_command


def _response(*, calls: list[tuple[str, str]]) -> AIMessage:
    """
    Собирает ответ модели с вызовами инструментов.

        calls: имя инструмента и команда каждого вызова.

    Возвращает: Ответ модели.
    """
    return AIMessage(
        content = "",
        tool_calls = [
            {"name": name, "args": {"command": command}, "id": f"call_{index}"}
            for index, (name, command) in enumerate(calls)
        ],
    )


@pytest.mark.parametrize(
    "command",
    ["echo DONE", 'echo "DONE"', "printf 'TODO'", "  echo TODO  "],
)
def test_answer_command_is_recognized(command: str) -> None:
    """
    Один echo или printf со словом DONE или TODO — попытка сдать работу командой.
    """
    assert _is_answer_command(response = _response(calls = [("bash", command)]))


@pytest.mark.parametrize(
    "calls",
    [
        # DONE рядом с другой командой
        [("bash", "make && echo DONE")],
        # DONE внутри другого текста
        [("bash", 'echo "Готово, DONE"')],
        # другой инструмент
        [("read", "echo DONE")],
        # среди вызовов есть обычная команда
        [("bash", "echo DONE"), ("bash", "ls")],
        # вызовов нет
        [],
    ],
)
def test_other_calls_are_not_answer_command(calls: list[tuple[str, str]]) -> None:
    """
    Команды с DONE рядом с другим текстом, другие инструменты и ответ без вызовов — не сдача командой.
    """
    assert not _is_answer_command(response = _response(calls = calls))


def test_not_model_response_is_not_answer_command() -> None:
    """
    Сообщение не от модели — не сдача командой.
    """
    assert not _is_answer_command(response = HumanMessage(content = "echo DONE"))
