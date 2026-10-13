"""Тесты уровня размышления: перевод в параметр think сервера ollama и клиент модели с выключенным размышлением."""

import pytest

from codeteam.common.llm import GenerationMode, OllamaConfig, ReasoningLevel, build_chat_model
from codeteam.common.llm.reasoning import ollama_think


@pytest.mark.parametrize(
    ("level", "think"),
    [
        (None, False),
        (ReasoningLevel.NONE, False),
        (ReasoningLevel.DEFAULT, True),
        (ReasoningLevel.LOW, "low"),
        (ReasoningLevel.MEDIUM, "medium"),
        (ReasoningLevel.HIGH, "high"),
    ],
)
def test_ollama_think(level: ReasoningLevel | None, think: bool | str) -> None:
    """
    Уровень переводится в think: выключенное размышление — False, уровень сервера — True, иначе имя уровня.
    """
    assert ollama_think(level = level) == think


@pytest.mark.parametrize("generation_mode", [GenerationMode.THINKING, GenerationMode.NON_THINKING])
def test_chat_model_without_reasoning(generation_mode: GenerationMode) -> None:
    """
    Клиент модели с уровнем NONE не просит размышления в любом режиме.
    """
    chat_model = build_chat_model(
        config = OllamaConfig(
            base_url = "http://127.0.0.1:11434",
            model = "qwen3.5:9b",
            context_window = 1000,
            max_output_tokens = 1000,
        ),
        generation_mode = generation_mode,
        reasoning_level = ReasoningLevel.NONE,
    )

    assert chat_model.reasoning is False
