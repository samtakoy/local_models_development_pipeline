"""Тесты проверки окна загруженных моделей: отличающееся окно находится, совпадающее, чужие модели и модели
без окна в ответе Ollama пропускаются."""

from codeteam.app.model_window_check import window_mismatches


def test_window_mismatches() -> None:
    """
    Находится только модель из настроек, загруженная с другим окном.
    """
    loaded_models = [
        {"name": "agent:35b", "context_length": 125000},
        {"name": "vision:4b", "context_length": 16000},
        {"name": "other:7b", "context_length": 8000},
        {"name": "old:1b"},
    ]
    expected_windows = {"agent:35b": 225000, "vision:4b": 16000, "old:1b": 4000}

    assert window_mismatches(loaded_models = loaded_models, expected_windows = expected_windows) == [
        ("agent:35b", 125000, 225000),
    ]


def test_no_loaded_models() -> None:
    """
    Загруженных моделей нет — отличий нет.
    """
    assert window_mismatches(loaded_models = [], expected_windows = {"agent:35b": 225000}) == []
