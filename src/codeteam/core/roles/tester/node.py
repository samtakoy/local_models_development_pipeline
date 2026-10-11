"""Узел тестировщика в графе пайплайна: финальная проверка готового приложения."""

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PipelineState
from codeteam.core.roles.common.final_check import run_final_check
from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.tester.prompts import TESTER_TASK


def tester_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает тестировщика после последнего этапа: он проверяет требования заказчика в готовом приложении
    и пишет вердикт с отчётом; если приложение не принято, команда получает этап исправлений.

        state: состояние пайплайна.
        config: конфигурация запуска с настройками пайплайна.

    Возвращает: Обновление состояния пайплайна.
    """
    return run_final_check(
        state = state,
        config = config,
        role = TESTER_ROLE,
        task_template = TESTER_TASK,
    )
