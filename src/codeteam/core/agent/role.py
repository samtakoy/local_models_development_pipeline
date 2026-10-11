"""Роль агента: настройки, с которыми пайплайн запускает агента."""

from dataclasses import dataclass

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.step_hooks import StepHook


@dataclass(frozen = True)
class AgentRole:
    """
    Настройки роли агента.

        name: имя роли; по нему назван агент в журнале.
        system_prompt: промпт роли: кто агент и как решает задачу.
        model_name: модель агента.
        reasoning_level: уровень размышления модели агента.
        tool_names: имена инструментов агента, одни и те же в фазе работы и в фазе черновика.
        step_hooks: хуки шага инструментов: замечания к изменённым файлам личной папки и к проекту.
        answer_checks: проверки сдачи: замечания к черновику, когда агент отвечает DONE.
        answer_file_names: заранее известные имена файлов ответа роли в черновике.
        only_answer_files: в черновике роли разрешены только файлы ответа.
    """

    name: str
    system_prompt: str
    model_name: str
    reasoning_level: ReasoningLevel
    tool_names: tuple[str, ...]
    step_hooks: tuple[StepHook, ...]
    answer_checks: tuple[AnswerCheck, ...]
    answer_file_names: tuple[str, ...]
    only_answer_files: bool
