"""Настройки приложения из переменных окружения и файла .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


@dataclass(frozen = True)
class Settings:
    """
    Настройки приложения.

        ollama_base_url: адрес сервера ollama без /v1.
        runs_dir: каталог папок прогонов: журналы запусков агентов; относительный путь считается
            от папки файла .env.
        prompts_db_dir: папка базы промптов: копии версий файлов промптов; относительный путь считается
            от папки файла .env.
        browser_headless: браузер агентов без окна; BROWSER_HEADLESS, не задана — без окна.
    """

    ollama_base_url: str
    agent_ctx_window: int
    runs_dir: Path
    prompts_db_dir: Path
    browser_headless: bool


def load_settings() -> Settings:
    """
    Читает настройки из окружения. Файл .env ищется вверх от текущего каталога; относительные пути
    из него считаются от папки файла, без файла — от текущего каталога.

    Возвращает: Настройки приложения.
    """
    dotenv_path = Path(find_dotenv(usecwd = True))
    load_dotenv(dotenv_path)

    return Settings(
        ollama_base_url = _require(name = "OLLAMA_BASE_URL"),
        agent_ctx_window = int(os.getenv("AGENT_CTX_WINDOW", 120000)),
        runs_dir = dotenv_path.parent / _require(name = "CODETEAM_RUNS_DIR"),
        prompts_db_dir = dotenv_path.parent / _require(name = "CODETEAM_PROMPTS_DB_DIR"),
        browser_headless = os.getenv("BROWSER_HEADLESS", "true").strip().lower() != "false",
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
