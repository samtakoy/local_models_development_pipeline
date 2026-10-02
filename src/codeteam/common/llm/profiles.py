"""Рекомендуемые параметры выборки моделей из их карточек."""

from dataclasses import dataclass
from enum import Enum


class GenerationMode(Enum):
    """Режим работы модели, для которого карточка задаёт свой набор параметров.

    Значения:
        THINKING: с размышлением, общие задачи.
        NON_THINKING: без размышления, общие задачи.
        NON_THINKING_REASONING: без размышления, задачи на рассуждение.
    """

    THINKING = "thinking"
    NON_THINKING = "non_thinking"
    NON_THINKING_REASONING = "non_thinking_reasoning"


@dataclass(frozen = True)
class SamplingProfile:
    """Набор параметров выборки для одного режима модели.

    Поля:
        temperature: температура.
        top_p: доля вероятности, в которой выбирается следующий токен.
        top_k: число кандидатов на следующий токен.
        min_p: минимальная вероятность кандидата относительно самого вероятного.
        presence_penalty: штраф за повтор уже встреченных токенов.
        repeat_penalty: множитель штрафа за повтор токенов.
    """

    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repeat_penalty: float


@dataclass(frozen = True)
class ModelProfile:
    """Рекомендуемые параметры одной модели.

    Поля:
        name: имя модели, по которому ищется профиль.
        source: адрес карточки модели.
        samplings: наборы параметров по режимам работы.
    """

    name: str
    source: str
    samplings: dict[GenerationMode, SamplingProfile]


PROFILES: tuple[ModelProfile, ...] = (
    ModelProfile(
        name = "qwen3.6-35b-a3b",
        source = "https://huggingface.co/Qwen/Qwen3.6-35B-A3B",
        samplings = {
            GenerationMode.THINKING: SamplingProfile(
                temperature = 1.0,
                top_p = 0.95,
                top_k = 20,
                min_p = 0.0,
                presence_penalty = 1.5,
                repeat_penalty = 1.0,
            ),
            GenerationMode.NON_THINKING: SamplingProfile(
                temperature = 0.7,
                top_p = 0.80,
                top_k = 20,
                min_p = 0.0,
                presence_penalty = 1.5,
                repeat_penalty = 1.0,
            ),
        },
    ),
    ModelProfile(
        name = "qwen3.5-9b",
        source = "https://huggingface.co/Qwen/Qwen3.5-9B",
        samplings = {
            GenerationMode.THINKING: SamplingProfile(
                temperature = 1.0,
                top_p = 0.95,
                top_k = 20,
                min_p = 0.0,
                presence_penalty = 1.5,
                repeat_penalty = 1.0,
            ),
            GenerationMode.NON_THINKING: SamplingProfile(
                temperature = 0.7,
                top_p = 0.8,
                top_k = 20,
                min_p = 0.0,
                presence_penalty = 1.5,
                repeat_penalty = 1.0,
            ),
            GenerationMode.NON_THINKING_REASONING: SamplingProfile(
                temperature = 1.0,
                top_p = 1.0,
                top_k = 40,
                min_p = 0.0,
                presence_penalty = 2.0,
                repeat_penalty = 1.0,
            ),
        },
    ),
    ModelProfile(
        name = "qwen3.8-27b",
        source = "https://ollama.com/library/qwen3.8:27b-mlx",
        samplings = {
            GenerationMode.THINKING: SamplingProfile(
                temperature = 1.0,
                top_p = 0.95,
                top_k = 20,
                min_p = 0.0,
                presence_penalty = 0.0,
                repeat_penalty = 1.0,
            ),
        },
    ),
)

# Знаки, которыми серверы разделяют части имени модели:
# qwen/qwen3.6-35b-a3b у LM Studio, qwen3.5:9b у ollama.
NAME_SEPARATORS = ("/", ":", "_", ".", "-", " ")


def normalize_model_name(*, model: str) -> str:
    """Приводит имя модели к виду для поиска профиля.

    Аргументы:
        model: имя модели как его знает сервер.

    Возвращает:
        Имя в нижнем регистре без разделителей.
    """
    name = model.lower()

    for separator in NAME_SEPARATORS:
        name = name.replace(separator, "")

    return name


def find_model_profile(*, model: str) -> ModelProfile | None:
    """Ищет профиль, имя которого входит в имя модели.

    Аргументы:
        model: имя модели как его знает сервер.

    Возвращает:
        Профиль с самым длинным совпавшим именем, None - когда совпадений нет.
    """
    normalized_model = normalize_model_name(model = model)
    matches = [
        profile
        for profile in PROFILES
        if normalize_model_name(model = profile.name) in normalized_model
    ]
    if not matches:
        return None

    return max(matches, key = lambda profile: len(profile.name))
