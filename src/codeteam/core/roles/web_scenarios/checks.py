"""Проверка сдачи составителя сценариев."""

from codeteam.core.agent.answer_checks import AnswerContext
from codeteam.core.roles.web_scenarios.launch import LaunchFileError, read_app_launch, scenario_files
from codeteam.core.roles.web_scenarios.prompts import NO_SCENARIOS_REMARK


def scenarios_check(context: AnswerContext) -> str | None:
    """
    Проверка сдачи составителя сценариев: файл запуска читается и есть хотя бы один файл сценария.

        context: сдача работы составителем сценариев.

    Возвращает: Замечание или None, если ответ годится.
    """
    try:
        read_app_launch(draft_dir = context.draft_dir)
    except LaunchFileError as error:
        return str(error)

    if not scenario_files(draft_dir = context.draft_dir):
        return NO_SCENARIOS_REMARK

    return None
