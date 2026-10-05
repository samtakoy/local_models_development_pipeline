"""
Проба: агент на локальной модели проходит веб-приложение как пользователь через Playwright MCP.

Запуск:
    uv run python scripts/browser_probe.py --model qwen3.5:9b --url http://127.0.0.1:5055 --task "..."
"""

import argparse
import asyncio
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from codeteam.app.settings import load_settings
from codeteam.common.llm import GenerationMode, OllamaConfig, ReasoningLevel, build_chat_model

# Имя сервера Playwright MCP в настройках клиента.
PLAYWRIGHT_SERVER_NAME = "playwright"

# Команда запуска Playwright MCP: браузер с окном, профиль только в памяти.
PLAYWRIGHT_SERVER = {
    "command": "npx",
    "args": ["@playwright/mcp@latest", "--isolated"],
    "transport": "stdio",
}

# Предел шагов графа агента: один вызов инструмента — два шага.
AGENT_STEP_LIMIT = 80

# Сколько символов результата инструмента выводить в консоль.
TOOL_RESULT_PREVIEW = 600

SYSTEM_PROMPT = """# Роль
Ты тестировщик веб-приложений. Ты проверяешь приложение так, как им пользуется человек.

## Задача
Выполни сценарий пользователя в браузере и опиши, что увидел.

## Для чего
По твоему отчёту команда поймёт, работает ли приложение для пользователя.

## Алгоритм
1. Открой адрес приложения.
2. Сними снимок страницы и найди на нём нужные элементы.
3. Выполняй шаги сценария по одному: действие, затем снимок, чтобы увидеть результат.
4. Когда сценарий пройден или дальше идти нельзя — напиши отчёт.

## Отчёт
- Какие шаги сценария выполнены и что на каждом было на странице.
- Что не сработало: шаг, ожидание, что произошло на самом деле.
- Итог: сценарий пройден или нет.

## Правила
- Элементы выбирай по снимку страницы: кликай и вводи текст по ссылке элемента из снимка.
- После каждого действия проверяй результат новым снимком.
- Пиши только то, что видел на странице.

## Запрещено
- Уходить с адреса приложения на другие сайты.
- Удалять данные приложения, если сценарий этого не требует.
- Придумывать результат шага, который не удалось выполнить."""


def parse_arguments() -> argparse.Namespace:
    """
    Читает аргументы командной строки.

    Возвращает: Модель, адрес приложения и сценарий.
    """
    parser = argparse.ArgumentParser(description = "Проба агента-тестировщика через Playwright MCP")
    parser.add_argument("--model", required = True, help = "имя модели в ollama")
    parser.add_argument("--url", required = True, help = "адрес приложения")
    parser.add_argument("--task", required = True, help = "сценарий пользователя")

    return parser.parse_args()


def message_text(message: BaseMessage) -> str:
    """
    Достаёт текст сообщения.

        message: сообщение агента или результата инструмента.

    Возвращает: Текст сообщения одной строкой.
    """
    content = message.content
    if isinstance(content, str):
        return content

    parts = [part.get("text", "") if isinstance(part, dict) else str(part) for part in content]

    return "\n".join(parts)


def print_message(message: BaseMessage) -> None:
    """
    Выводит в консоль шаг агента: ответ модели, вызовы инструментов или их результат.

        message: новое сообщение графа агента.
    """
    if isinstance(message, AIMessage):
        text = message_text(message).strip()
        if text:
            print(f"\n[модель] {text}")
        for tool_call in message.tool_calls:
            print(f"[вызов] {tool_call['name']} {tool_call['args']}")
        return

    if isinstance(message, ToolMessage):
        text = message_text(message)
        print(f"[результат {message.name}, символов {len(text)}] {text[:TOOL_RESULT_PREVIEW]}")


async def run_probe(*, model: str, url: str, task: str) -> None:
    """
    Запускает агента-тестировщика на сценарии и выводит его шаги в консоль.

        model: имя модели в ollama.
        url: адрес приложения.
        task: сценарий пользователя.
    """
    settings = load_settings()
    chat_model = build_chat_model(
        config = OllamaConfig(
            base_url = settings.ollama_base_url,
            model = model,
            context_window = settings.agent_ctx_window,
        ),
        generation_mode = GenerationMode.THINKING,
        reasoning_level = ReasoningLevel.LOW,
    )

    client = MultiServerMCPClient({PLAYWRIGHT_SERVER_NAME: PLAYWRIGHT_SERVER})
    # Одна сессия на весь прогон: браузер и открытая страница живут между вызовами инструментов
    async with client.session(PLAYWRIGHT_SERVER_NAME) as session:
        tools = await load_mcp_tools(session)
        print(f"[инструменты] {', '.join(tool.name for tool in tools)}")

        agent = create_agent(model = chat_model, tools = tools, system_prompt = SYSTEM_PROMPT)
        request = f"Адрес приложения: {url}\n\nСценарий:\n{task}"

        async for update in agent.astream(
            {"messages": [{"role": "user", "content": request}]},
            config = {"recursion_limit": AGENT_STEP_LIMIT},
            stream_mode = "updates",
        ):
            for node_update in update.values():
                for message in (node_update or {}).get("messages", []):
                    print_message(message)


def main() -> None:
    """
    Точка входа пробы.
    """
    # Вывод построчно: шаги видны в файле журнала сразу, а не в конце прогона
    sys.stdout.reconfigure(line_buffering = True)
    arguments = parse_arguments()
    asyncio.run(run_probe(model = arguments.model, url = arguments.url, task = arguments.task))


if __name__ == "__main__":
    main()
