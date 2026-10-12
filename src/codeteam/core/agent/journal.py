"""Журнал запуска агента: ход графа в md-файл для человека и строка на каждый шаг в консоль."""

import html
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES

# Наносекунд в секунде: ollama отдаёт длительности в наносекундах.
NANOSECONDS_PER_SECOND = 1_000_000_000

# Серия обратных кавычек в тексте: ограда кода должна быть длиннее самой длинной серии.
_BACKTICK_RUN_PATTERN = re.compile(r"`+")

logger = logging.getLogger(__name__)


class AgentJournal:
    """
    Пишет ход одного запуска агента: md-файл для человека и строку на каждый шаг в консоль.

    Получает события графа в режиме updates: {имя узла: {"messages": [...]}}. Каждый шаг сразу
    дописывается в файл, поэтому журнал можно читать во время прогона.
    """

    def __init__(self, *, path: Path, agent_name: str, model_name: str) -> None:
        """
        Создаёт файл журнала и пишет заголовок.

            path: файл журнала; папка создаётся, если её нет.
            agent_name: имя агента для заголовка и строк консоли.
            model_name: имя модели агента.
        """
        self._path = path
        self._agent_name = agent_name
        self._started_at = time.monotonic()
        self._step_count = 0
        self._model_request_count = 0
        self._input_tokens = 0
        self._output_tokens = 0

        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_text(
            f"# {agent_name} · {datetime.now():%Y-%m-%d %H:%M:%S}\n\n- модель: `{model_name}`\n",
            encoding = "utf-8",
        )

    def write_tools(self, *, tools: list[dict[str, Any]]) -> None:
        """
        Пишет инструменты в том виде, в каком их получает модель.

            tools: описания инструментов из привязанного клиента модели.
        """
        names = ", ".join(tool["function"]["name"] for tool in tools)
        rendered = _code_block(text = json.dumps(tools, ensure_ascii = False, indent = 2))
        self._append(text = f"\n## Инструменты модели · {names}\n\n{rendered}\n")
        logger.info(f"[{self._agent_name}] инструменты: {names}")

    def write(self, *, event: dict[str, Any]) -> None:
        """
        Пишет шаг графа: раздел на каждый узел события с его сообщениями.

            event: событие графа в режиме updates.
        """
        for node_name, update in event.items():
            messages = update.get("messages", []) if isinstance(update, dict) else []
            self._step_count += 1
            self._count_model_requests(messages = messages)

            summary = _step_summary(messages = messages)
            title = " · ".join([f"{self._step_count}. {node_name}", *summary])
            rendered = [_render_message(message = message) for message in messages]
            self._append(text = f"\n## {title}\n\n" + "\n\n".join(rendered) + "\n")
            logger.info(f"[{self._agent_name}] {title}")

    def write_error(self, *, error: Exception) -> None:
        """
        Пишет ошибку, прервавшую запуск.

            error: исключение.
        """
        self._append(text = f"\n## Ошибка\n\n{_code_block(text = f'{type(error).__name__}: {error}')}\n")
        logger.error(f"[{self._agent_name}] ошибка: {type(error).__name__}: {error}")

    def finish(self) -> None:
        """
        Пишет итог запуска: шаги, запросы к модели, токены и время.
        """
        elapsed_seconds = time.monotonic() - self._started_at
        self._append(
            text = (
                "\n## Итог\n\n"
                f"- шагов: {self._step_count}\n"
                f"- запросов к модели: {self._model_request_count}\n"
                f"- токены: вход {self._input_tokens}, выход {self._output_tokens}\n"
                f"- время: {elapsed_seconds:.1f} с\n"
            )
        )
        logger.info(
            f"[{self._agent_name}] итог: шагов {self._step_count}, запросов к модели {self._model_request_count}, "
            f"токены {self._input_tokens}/{self._output_tokens}, {elapsed_seconds:.1f} с, журнал {self._path}"
        )

    def _count_model_requests(self, *, messages: list[BaseMessage]) -> None:
        """
        Прибавляет к счётчикам запросы к модели и их токены.

            messages: сообщения шага; ответ модели — AIMessage с usage_metadata.
        """
        for message in messages:
            if isinstance(message, AIMessage) and message.usage_metadata:
                self._model_request_count += 1
                self._input_tokens += message.usage_metadata["input_tokens"]
                self._output_tokens += message.usage_metadata["output_tokens"]

    def _append(self, *, text: str) -> None:
        """
        Дописывает текст в файл журнала.

            text: текст markdown.
        """
        with self._path.open("a", encoding = "utf-8") as file:
            file.write(text)


def _step_summary(*, messages: list[BaseMessage]) -> list[str]:
    """
    Собирает короткое описание шага для заголовка раздела и строки консоли.

        messages: сообщения шага.

    Возвращает: Части описания: время и токены ответа модели, вызовы, результаты инструментов, длина ответа.
    """
    parts: list[str] = []
    called_tools: list[str] = []
    answered_tools: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            parts.extend(_model_metrics(message = message))
            called_tools.extend(call["name"] for call in message.tool_calls)
            if message.text and not message.tool_calls:
                parts.append(f"ответ: знаков {len(message.text)}")
        elif isinstance(message, ToolMessage):
            answered_tools.append(f"{message.name} (ошибка)" if message.status == "error" else str(message.name))
        elif isinstance(message, RemoveMessage) and message.id == REMOVE_ALL_MESSAGES:
            parts.append("история очищена")

    if called_tools:
        parts.append(f"вызовы: {', '.join(called_tools)}")

    if answered_tools:
        parts.append(f"результаты: {', '.join(answered_tools)}")

    return parts


def _model_metrics(*, message: AIMessage) -> list[str]:
    """
    Достаёт время и токены ответа модели.

        message: сообщение модели.

    Возвращает: Время ответа и токены вход/выход; пустой список для сообщения не от модели.
    """
    parts: list[str] = []
    total_duration = message.response_metadata.get("total_duration")
    if total_duration:
        parts.append(f"{total_duration / NANOSECONDS_PER_SECOND:.1f} с")

    if message.usage_metadata:
        parts.append(f"токены {message.usage_metadata['input_tokens']}/{message.usage_metadata['output_tokens']}")

    return parts


def _render_message(*, message: BaseMessage) -> str:
    """
    Оформляет сообщение для журнала.

        message: сообщение графа.

    Возвращает: Текст markdown.
    """
    if isinstance(message, RemoveMessage):
        if message.id == REMOVE_ALL_MESSAGES:
            return "**История очищена**, дальше — новая история."

        return f"Удалено сообщение {_inline_code(text = str(message.id))}"

    if isinstance(message, SystemMessage):
        return _folded(summary = "системный промпт", body = _quote(text = message.text))

    if isinstance(message, HumanMessage):
        return f"**Задача**\n\n{_quote(text = message.text)}"

    if isinstance(message, AIMessage):
        return _render_ai_message(message = message)

    if isinstance(message, ToolMessage):
        return _render_tool_message(message = message)

    return f"**{message.type}**\n\n{_quote(text = message.text)}"


def _render_ai_message(*, message: AIMessage) -> str:
    """
    Оформляет сообщение модели: размышление, ответ, вызовы инструментов.

        message: сообщение модели.

    Возвращает: Текст markdown.
    """
    parts: list[str] = []
    reasoning = message.additional_kwargs.get("reasoning_content")
    if reasoning:
        parts.append(_folded(summary = "размышление", body = _quote(text = reasoning)))

    if message.text:
        parts.append(_quote(text = message.text))

    if message.tool_calls:
        calls = [
            f"- {_inline_code(text = call['name'])} {_inline_code(text = json.dumps(call['args'], ensure_ascii = False))}"
            for call in message.tool_calls
        ]
        parts.append("Вызовы:\n" + "\n".join(calls))

    if message.invalid_tool_calls:
        invalid_calls = [
            f"- {_inline_code(text = str(call.get('name')))} {_inline_code(text = str(call.get('args')))}: "
            f"{call.get('error')}"
            for call in message.invalid_tool_calls
        ]
        parts.append("Неразобранные вызовы:\n" + "\n".join(invalid_calls))

    if not parts:
        return "*пустой ответ*"

    return "\n\n".join(parts)


def _render_tool_message(*, message: ToolMessage) -> str:
    """
    Оформляет результат инструмента свёрнутым блоком.

        message: результат инструмента.

    Возвращает: Текст markdown.
    """
    text = message.text
    status = "ошибка · " if message.status == "error" else ""
    summary = f"{status}{message.name} · строк {len(text.splitlines())}"

    return _folded(summary = summary, body = _code_block(text = text))


def _folded(*, summary: str, body: str) -> str:
    """
    Оформляет сворачиваемый блок.

        summary: подпись блока.
        body: содержимое блока, markdown.

    Возвращает: Блок <details>.
    """
    return f"<details><summary>{html.escape(summary)}</summary>\n\n{body}\n\n</details>"


def _quote(*, text: str) -> str:
    """
    Оформляет текст цитатой, «<» заменяет на «&lt;»: теги из текста предпросмотр показывает текстом.

        text: текст.

    Возвращает: Текст, где каждая строка начинается с «> ».
    """
    escaped_text = text.replace("<", "&lt;")

    return "\n".join(f"> {line}" if line else ">" for line in escaped_text.splitlines())


def _code_block(*, text: str) -> str:
    """
    Оформляет текст блоком кода.

        text: текст.

    Возвращает: Блок кода с оградой длиннее любой серии обратных кавычек в тексте.
    """
    fence = _fence(text = text, minimum_length = 3)

    return f"{fence}\n{text}\n{fence}"


def _inline_code(*, text: str) -> str:
    """
    Оформляет текст кодом в строке.

        text: текст.

    Возвращает: Текст в обратных кавычках, которых больше, чем в любой серии внутри текста.
    """
    fence = _fence(text = text, minimum_length = 1)

    return f"{fence} {text} {fence}"


def _fence(*, text: str, minimum_length: int) -> str:
    """
    Подбирает ограду из обратных кавычек.

        text: текст внутри ограды.
        minimum_length: наименьшая длина ограды.

    Возвращает: Обратные кавычки: на одну больше самой длинной серии в тексте, но не меньше minimum_length.
    """
    longest_run = max((len(run) for run in _BACKTICK_RUN_PATTERN.findall(text)), default = 0)

    return "`" * max(minimum_length, longest_run + 1)
