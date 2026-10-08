"""Роль агента: настройки, с которыми пайплайн запускает агента."""

from dataclasses import dataclass

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.step_hooks import StepCheck, StepHook


@dataclass(frozen = True)
class AgentRole:
    """
    Настройки роли агента.

        name: имя роли; по нему назван агент в журнале.
        system_prompt: промпт роли: кто агент и как решает задачу.
        model_name: модель агента.
        reasoning_level: уровень размышления модели агента.
        tool_names: имена инструментов агента, одни и те же в фазе работы и в фазе черновика.
        step_hooks: хуки после шага инструментов: замечания к изменённым файлам черновика.
        step_checks: проверки после шага инструментов: замечания не к черновику, а, например, к проекту.
        answer_checks: проверки сдачи: замечания к черновику, когда агент отвечает DONE.
    """

    name: str
    system_prompt: str
    model_name: str
    reasoning_level: ReasoningLevel
    tool_names: tuple[str, ...]
    step_hooks: tuple[StepHook, ...]
    step_checks: tuple[StepCheck, ...]
    answer_checks: tuple[AnswerCheck, ...]
