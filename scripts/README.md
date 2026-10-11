# browser_probe.py

Проба агента-тестировщика: локальная модель проходит веб-приложение как пользователь через Playwright MCP
и пишет отчёт по шагам сценария.

## Что нужно

- Google Chrome.
- Node.js с `npx`: Playwright MCP скачивается и запускается командой `npx @playwright/mcp@latest`.
- Сервер ollama с моделью; адрес и окно контекста берутся из `.env` codeteam.
- Зависимости для разработки: `uv sync` (пакет `langchain-mcp-adapters`).

## Запуск

1. Запустить проверяемое приложение и узнать его адрес.
2. Запустить пробу из папки codeteam_v2:

```bash
uv run python scripts/browser_probe.py \
    --model qwen3.5:9b \
    --url http://127.0.0.1:5055 \
    --task "Открой главную страницу, открой любую колоду, покажи ответ первой карточки, перейди к следующей карточке. Опиши, что было на экране на каждом шаге."
```

Аргументы:
- `--model` — имя модели в ollama;
- `--url` — адрес приложения;
- `--task` — сценарий пользователя.

## Что выводит

- `[инструменты]` — инструменты Playwright MCP, выданные агенту;
- `[вызов]` — вызов инструмента с аргументами;
- `[результат ...]` — размер результата в символах и его начало;
- `[модель]` — текст модели, в конце — отчёт по сценарию.

Окно Chrome открывается при первом переходе на страницу и может оказаться на заднем плане.

Снимки страниц и журналы консоли Playwright MCP пишет в папку `.playwright-mcp/` в папке запуска.

## Пример: эталонный cards

Запуск на копии библиотеки, чтобы агент не менял настоящую:

```bash
cd /Users/samtakot/devs/learnings/DLS/notebooks/cards
cp data/library.json /tmp/probe_library.json
CARDVIEWER_LIBRARY=/tmp/probe_library.json CARDVIEWER_PORT=5055 CARDVIEWER_DEBUG=0 .venv/bin/cardviewer
```

# run_stats.py

Пересобирает отчёт статистики прогона `stats_report.md` из файлов `*.stats.json` в папке прогона
и печатает путь к отчёту. Запуск из папки codeteam_v2:

```bash
uv run python scripts/run_stats.py runs/<прогон>
```
