"""Проверка окна контекста моделей, уже загруженных в Ollama: загруженная модель работает с окном, с которым её
загрузили, пока её не выгрузят."""

import logging
from typing import Any

import httpx

from codeteam.app.settings import Settings

logger = logging.getLogger(__name__)

# Предел ожидания ответа Ollama о загруженных моделях, секунды.
LOADED_MODELS_TIMEOUT_SECONDS = 5


def warn_loaded_window_mismatch(*, settings: Settings) -> None:
    """
    Пишет предупреждение, если модель агентов или смотрящая модель уже загружена в Ollama с другим окном контекста.
    Ollama не ответил — пишет, что проверка пропущена.

        settings: настройки приложения.
    """
    expected_windows = {settings.agent_model: settings.agent_ctx_window}
    if settings.vision_model is not None:
        expected_windows.setdefault(settings.vision_model, settings.vision_ctx_window)

    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/ps", timeout = LOADED_MODELS_TIMEOUT_SECONDS)
        response.raise_for_status()
        loaded_models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError) as error:
        logger.info(f"[ollama] окно загруженных моделей не проверено: {error}")
        return

    for model, loaded_window, expected_window in window_mismatches(
        loaded_models = loaded_models,
        expected_windows = expected_windows,
    ):
        logger.warning(
            f"[ollama] модель {model} уже загружена с окном {loaded_window}, в настройках — {expected_window}: "
            f"модель работает со старым окном, пока её не выгрузят: ollama stop {model}"
        )


def window_mismatches(
    *,
    loaded_models: list[dict[str, Any]],
    expected_windows: dict[str, int],
) -> list[tuple[str, int, int]]:
    """
    Находит загруженные модели, окно контекста которых отличается от настроек.

        loaded_models: модели из ответа Ollama /api/ps: поля name и context_length.
        expected_windows: окно контекста из настроек по имени модели.

    Возвращает: Для каждой отличающейся модели — имя, окно в Ollama и окно из настроек.
    """
    mismatches = []
    for loaded_model in loaded_models:
        name = loaded_model["name"]
        loaded_window = loaded_model.get("context_length")
        if name in expected_windows and loaded_window is not None and loaded_window != expected_windows[name]:
            mismatches.append((name, loaded_window, expected_windows[name]))

    return mismatches
