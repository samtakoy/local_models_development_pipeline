"""Сервер документации Context7 MCP для советника: поиск библиотеки и запрос к её документации."""

import logging
from pathlib import Path

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from codeteam.core.roles.common import CallerContext, PipelineError
from codeteam.core.roles.common.npx import NPX_COMMAND, npx_args
from codeteam.core.tools.mcp import McpServer, McpTools

# Пакет Context7 MCP с закреплённой версией: запускается через npx.
# От версии зависит RESOLVE_LIBRARY_FOUND: при смене версии сверить его с ответом resolve-library-id новой версии.
CONTEXT7_MCP_PACKAGE = "@upstash/context7-mcp@4.1.1"

# Аргументы запуска: -y — скачать пакет без вопроса.
CONTEXT7_ARGS = ("-y", CONTEXT7_MCP_PACKAGE)

# Переменная окружения сервера с ключом Context7.
CONTEXT7_API_KEY_ENV_NAME = "CONTEXT7_API_KEY"

# Инструмент сервера: найти библиотеку по имени и получить её идентификатор Context7.
RESOLVE_LIBRARY_TOOL_NAME = "resolve-library-id"

# Инструмент сервера: запрос к документации библиотеки по её идентификатору.
QUERY_DOCS_TOOL_NAME = "query-docs"

# Пробный поиск библиотеки, которым проверяется ключ Context7.
KEY_PROBE_LIBRARY_NAME = "Flask"
KEY_PROBE_QUERY = "quickstart"

# Начало ответа resolve-library-id версии CONTEXT7_MCP_PACKAGE, когда библиотеки найдены.
RESOLVE_LIBRARY_FOUND = "Available Libraries:"

logger = logging.getLogger(__name__)


def context7_server(caller_context: CallerContext) -> McpServer:
    """
    Собирает сервер Context7 MCP для запуска советника.

        caller_context: агент, которому нужна документация.

    Возвращает: Сервер MCP из своего кэша npm: работает в папке проекта, вызовы не проверяются.
    """
    return _build_server(
        npm_cache_dir = caller_context.cfg.settings.npm_cache_dir,
        api_key = caller_context.cfg.settings.context7_api_key,
        work_dir = Path(caller_context.cfg.project_path),
    )


def warm_up_documentation(*, work_dir: Path, npm_cache_dir: Path, api_key: str | None, check_key: bool) -> None:
    """
    Скачивает Context7 MCP в свой кэш npm, запускает сервер и проверяет, что у него есть инструменты советника;
    если задана проверка ключа — ещё и ключ пробным поиском библиотеки. Ошибку поднимает PipelineError.

        work_dir: рабочая папка сервера; создаётся, если её нет.
        npm_cache_dir: свой кэш npm.
        api_key: ключ Context7; None — без ключа.
        check_key: проверить ключ пробным поиском библиотеки.
    """
    if check_key and api_key is None:
        raise PipelineError(f"CONTEXT7_CHECK_KEY_AT_START=true, а {CONTEXT7_API_KEY_ENV_NAME} в .env не задан")

    logger.info(f"[документация] прогрев {CONTEXT7_MCP_PACKAGE}: скачивание и запуск сервера")
    work_dir.mkdir(parents = True, exist_ok = True)
    server = _build_server(npm_cache_dir = npm_cache_dir, api_key = api_key, work_dir = work_dir)
    try:
        with McpTools(servers = (server,)) as tools:
            tools_by_name = {tool.name: tool for tool in tools}
            missing_names = sorted({RESOLVE_LIBRARY_TOOL_NAME, QUERY_DOCS_TOOL_NAME} - tools_by_name.keys())
            key_failure = (
                _probe_key(resolve_tool = tools_by_name[RESOLVE_LIBRARY_TOOL_NAME])
                if check_key and not missing_names
                else None
            )
    except (RuntimeError, TimeoutError) as error:
        raise PipelineError(
            f"Context7 MCP не запустился: {error}. Ошибка npm — в выводе выше; советнику по документации "
            f"нужны Node.js с npx и доступ в интернет"
        ) from error

    if missing_names:
        raise PipelineError(f"у Context7 MCP нет инструментов {', '.join(missing_names)}")

    if key_failure is not None:
        raise PipelineError(f"ключ Context7 не подошёл: {key_failure}")

    logger.info("[документация] готова")


def _probe_key(*, resolve_tool: BaseTool) -> str | None:
    """
    Ищет пробную библиотеку инструментом resolve-library-id.

        resolve_tool: инструмент resolve-library-id сервера.

    Возвращает: Ответ сервера, если библиотеки не найдены; None, если поиск прошёл.
    """
    answer: ToolMessage = resolve_tool.invoke({
        "type": "tool_call",
        "id": "key_probe",
        "name": RESOLVE_LIBRARY_TOOL_NAME,
        "args": {"query": KEY_PROBE_QUERY, "libraryName": KEY_PROBE_LIBRARY_NAME},
    })
    if answer.status != "error" and answer.text.startswith(RESOLVE_LIBRARY_FOUND):
        return None

    return answer.text


def _build_server(*, npm_cache_dir: Path, api_key: str | None, work_dir: Path) -> McpServer:
    """
    Собирает сервер Context7 MCP.

        npm_cache_dir: свой кэш npm.
        api_key: ключ Context7; None — без ключа.
        work_dir: рабочая папка сервера.

    Возвращает: Сервер MCP без проверки вызовов; с ключом — ключ в окружении сервера.
    """
    return McpServer(
        name = "context7",
        command = NPX_COMMAND,
        args = npx_args(npm_cache_dir = npm_cache_dir, package_args = CONTEXT7_ARGS),
        cwd = work_dir,
        env = {CONTEXT7_API_KEY_ENV_NAME: api_key} if api_key is not None else {},
        check_call = None,
        excluded_tool_names = (),
    )
