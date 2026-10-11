"""Узел веб-тестировщика в графе пайплайна: финальная проверка готового приложения в браузере."""

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PipelineState
from codeteam.core.roles.common.final_check import run_final_check
from codeteam.core.roles.web_tester.config import WEB_TESTER_ROLE
from codeteam.core.roles.web_tester.prompts import WEB_TESTER_TASK


def web_tester_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает веб-тестировщика после последнего этапа: он проходит требования заказчика в браузере
    и пишет вердикт с отчётом; если приложение не принято, команда получает этап исправлений.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния пайплайна.
    """
    return run_final_check(
        state = state,
        config = config,
        role = WEB_TESTER_ROLE,
        task_template = WEB_TESTER_TASK,
    )
