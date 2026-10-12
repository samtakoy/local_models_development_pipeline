"""Роль агента: настройки, с которыми пайплайн запускает агента."""

from dataclasses import dataclass

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.answer_files import AnswerFiles
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
        answer_files: файлы ответа роли в черновике: по ним собираются правила черновика в общих инструкциях.
        step_hooks: все хуки шага инструментов роли, включая общие: места и имена файлов личной папки,
            подсказка фазы черновика.
        answer_checks: проверки сдачи: замечания к черновику, когда агент отвечает DONE.
    """

    name: str
    system_prompt: str
    model_name: str
    reasoning_level: ReasoningLevel
    tool_names: tuple[str, ...]
    answer_files: AnswerFiles
    step_hooks: tuple[StepHook, ...]
    answer_checks: tuple[AnswerCheck, ...]
