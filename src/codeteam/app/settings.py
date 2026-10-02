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
        runs_dir: каталог папок прогонов: журналы запусков агентов.
    """

    ollama_base_url: str
    agent_ctx_window: int
    runs_dir: Path


def load_settings() -> Settings:
    """
    Читает настройки из окружения. Файл .env ищется вверх от текущего каталога.

    Возвращает: Настройки приложения.
    """
    load_dotenv(find_dotenv(usecwd = True))

    return Settings(
        ollama_base_url = _require(name = "OLLAMA_BASE_URL"),
        agent_ctx_window = int(os.getenv("AGENT_CTX_WINDOW", 120000)),
        runs_dir = Path(_require(name = "CODETEAM_RUNS_DIR")),
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
