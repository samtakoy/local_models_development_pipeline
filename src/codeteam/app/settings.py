"""Настройки приложения из переменных окружения и файла .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Папка своего кэша npm рядом с файлом .env: в неё npx скачивает пакеты серверов MCP.
NPM_CACHE_DIR_NAME = ".npm-cache"

# Начало имён переменных окружения, которые передаются серверу Playwright MCP.
PLAYWRIGHT_MCP_ENVIRONMENT_PREFIX = "PLAYWRIGHT_MCP_"


@dataclass(frozen = True)
class Settings:
    """
    Настройки приложения.

        ollama_base_url: адрес сервера ollama без /v1.
        agent_model: модель агентов команды; AGENT_MODEL.
        runs_dir: каталог папок прогонов: журналы запусков агентов; относительный путь считается
            от папки файла .env.
        prompts_db_dir: папка базы промптов: копии версий файлов промптов; относительный путь считается
            от папки файла .env.
        vision_model: модель, которая смотрит картинки для инструмента describe_picture; VISION_MODEL,
            не задана — инструмента нет.
        vision_ctx_window: окно контекста смотрящей модели в токенах; VISION_CTX_WINDOW, не задана — окно агентов.
        browser_headless: браузер агентов без окна; BROWSER_HEADLESS, не задана — без окна.
        context7_api_key: ключ Context7 для советника по документации; CONTEXT7_API_KEY, не задан — Context7
            без ключа, с меньшими лимитами.
        context7_check_key_at_start: перед первой ролью проверить ключ Context7 пробным поиском библиотеки;
            CONTEXT7_CHECK_KEY_AT_START, не задана — без проверки.
        npm_cache_dir: свой кэш npm, куда npx скачивает пакеты серверов MCP: папка NPM_CACHE_DIR_NAME рядом
            с файлом .env.
        playwright_mcp_environment: переменные окружения сервера Playwright MCP: переменные процесса
            с началом имени PLAYWRIGHT_MCP_ENVIRONMENT_PREFIX.
    """

    ollama_base_url: str
    agent_model: str
    agent_ctx_window: int
    runs_dir: Path
    prompts_db_dir: Path
    vision_model: str | None
    vision_ctx_window: int
    browser_headless: bool
    context7_api_key: str | None
    context7_check_key_at_start: bool
    npm_cache_dir: Path
    playwright_mcp_environment: dict[str, str]


def load_settings() -> Settings:
    """
    Читает настройки из окружения. Файл .env ищется вверх от текущего каталога; относительные пути
    из него считаются от папки файла, без файла — от текущего каталога.

    Возвращает: Настройки приложения.
    """
    dotenv_path = Path(find_dotenv(usecwd = True))
    load_dotenv(dotenv_path)
    agent_ctx_window = int(os.getenv("AGENT_CTX_WINDOW", 120000))

    return Settings(
        ollama_base_url = _require(name = "OLLAMA_BASE_URL"),
        agent_model = _require(name = "AGENT_MODEL"),
        agent_ctx_window = agent_ctx_window,
        runs_dir = dotenv_path.parent / _require(name = "CODETEAM_RUNS_DIR"),
        prompts_db_dir = dotenv_path.parent / _require(name = "CODETEAM_PROMPTS_DB_DIR"),
        vision_model = os.getenv("VISION_MODEL", "").strip() or None,
        vision_ctx_window = int(os.getenv("VISION_CTX_WINDOW", agent_ctx_window)),
        browser_headless = os.getenv("BROWSER_HEADLESS", "true").strip().lower() != "false",
        context7_api_key = os.getenv("CONTEXT7_API_KEY", "").strip() or None,
        context7_check_key_at_start = os.getenv("CONTEXT7_CHECK_KEY_AT_START", "false").strip().lower() == "true",
        npm_cache_dir = dotenv_path.parent / NPM_CACHE_DIR_NAME,
        playwright_mcp_environment = {
            name: value for name, value in os.environ.items() if name.startswith(PLAYWRIGHT_MCP_ENVIRONMENT_PREFIX)
        },
    )


def _require(*, name: str) -> str:
    """
    Читает обязательную переменную окружения.

        name: имя переменной.

    Возвращает: Значение переменной.
    """
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name}: добавьте её в .env")

    return value
