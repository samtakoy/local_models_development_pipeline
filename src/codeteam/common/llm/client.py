"""Клиент модели сервера ollama на рекомендуемых параметрах выборки режима."""

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

from codeteam.common.llm.profiles import GenerationMode, SamplingProfile, find_model_profile
from codeteam.common.llm.reasoning import ReasoningLevel, ollama_think

# Потолок ожидания ответа. Локальная модель на слабой машине думает минутами.
REQUEST_TIMEOUT_SECONDS = 600

# Число повторов неудачного подключения к серверу.
MAX_RETRIES = 1

logger = logging.getLogger(__name__)


@dataclass(frozen = True)
class OllamaConfig:
    """
    Настройки сервера ollama.

        base_url: адрес сервера без /v1.
        model: имя модели как его знает сервер.
        context_window: окно контекста модели в токенах (num_ctx); без него ollama берёт 32768.
        max_output_tokens: предел токенов одного ответа модели вместе с размышлением (num_predict).
    """

    base_url: str
    model: str
    context_window: int
    max_output_tokens: int


class ChatOllamaWithSampling(ChatOllama):
    """
    Клиент ollama, передающий min_p и presence_penalty в options запроса.

        min_p: минимальная вероятность кандидата относительно самого вероятного.
        presence_penalty: штраф за повтор уже встреченных токенов.
    """

    min_p: float | None = None
    presence_penalty: float | None = None

    def _chat_params(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Собирает параметры запроса, добавляя min_p и presence_penalty в options.

            messages: сообщения разговора.
            stop: последовательности остановки.
            **kwargs: параметры вызова.

        Возвращает: Параметры запроса к ollama.
        """
        params = super()._chat_params(messages, stop, **kwargs)

        options = dict(params.get("options") or {})
        for name, value in (("min_p", self.min_p), ("presence_penalty", self.presence_penalty)):
            if value is not None:
                options.setdefault(name, value)
        params["options"] = options

        return params


def build_chat_model(
    *,
    config: OllamaConfig,
    generation_mode: GenerationMode,
    reasoning_level: ReasoningLevel,
) -> BaseChatModel:
    """
    Собирает клиент модели на рекомендуемых параметрах выборки режима.

    Размышление включено только в режиме THINKING. Когда у модели нет профиля
    или набора для режима, параметры выборки берутся из настроек сервера.

        config: настройки сервера ollama.
        generation_mode: режим работы модели.
        reasoning_level: уровень размышления для режима THINKING.

    Возвращает: Клиент модели.
    """
    sampling = _find_sampling(model = config.model, generation_mode = generation_mode)
    level = reasoning_level if generation_mode is GenerationMode.THINKING else None

    return ChatOllamaWithSampling(
        base_url = config.base_url,
        model = config.model,
        num_ctx = config.context_window,
        num_predict = config.max_output_tokens,
        reasoning = ollama_think(level = level),
        client_kwargs = {"timeout": REQUEST_TIMEOUT_SECONDS},
        sync_client_kwargs = {"transport": httpx.HTTPTransport(retries = MAX_RETRIES)},
        async_client_kwargs = {"transport": httpx.AsyncHTTPTransport(retries = MAX_RETRIES)},
        **_sampling_parameters(sampling = sampling),
    )


def describe_chat_model(*, config: OllamaConfig) -> str:
    """
    Описывает модель строкой для журнала запуска.

        config: настройки сервера ollama.

    Возвращает: Строку вида "qwen3.5:9b | http://127.0.0.1:11434 | окно 102400 | профиль qwen3.5-9b".
    """
    profile = find_model_profile(model = config.model)
    profile_name = profile.name if profile else "не найден"

    return f"{config.model} | {config.base_url} | окно {config.context_window} | профиль {profile_name}"


def _find_sampling(*, model: str, generation_mode: GenerationMode) -> SamplingProfile | None:
    """
    Ищет набор параметров выборки модели для режима.

    Когда набора нет, пишет предупреждение в журнал.

        model: имя модели как его знает сервер.
        generation_mode: режим работы модели.

    Возвращает: Набор параметров, None - когда у модели нет профиля или набора для режима.
    """
    profile = find_model_profile(model = model)
    sampling = profile.samplings.get(generation_mode) if profile else None

    if sampling is None:
        logger.warning(
            f"Нет параметров выборки для модели {model!r} в режиме "
            f"{generation_mode.value}: берутся настройки сервера"
        )

    return sampling


def _sampling_parameters(*, sampling: SamplingProfile | None) -> dict[str, float | None]:
    """
    Переводит набор параметров выборки в поля клиента.

        sampling: набор параметров, None - параметры не передаются.

    Возвращает: Поля клиента по именам.
    """
    if sampling is None:
        return {}

    return {
        "temperature": sampling.temperature,
        "top_p": sampling.top_p,
        "top_k": sampling.top_k,
        "min_p": sampling.min_p,
        "presence_penalty": sampling.presence_penalty,
        "repeat_penalty": sampling.repeat_penalty,
    }
