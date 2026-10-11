"""Хуки шага помощника с браузером."""

import random

from codeteam.core.agent.statistics import WORK_PHASE
from codeteam.core.agent.step_hooks import StepContext
from codeteam.core.roles.browser_checker.prompts import BROWSER_CHECKER_REFUSAL_HINTS


def browser_checker_refusal_hook(context: StepContext) -> str | None:
    """
    Хук шага помощника с браузером: в фазе работы к отказам файловых инструментов по пути — одна из его подсказок.

        context: шаг инструментов.

    Возвращает: Подсказку или None, если шаг не в фазе работы или отказов не было.
    """
    if context.phase != WORK_PHASE or not context.refusals:
        return None

    return random.choice(BROWSER_CHECKER_REFUSAL_HINTS)
