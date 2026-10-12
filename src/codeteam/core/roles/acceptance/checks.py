"""Проверки сдачи итоговой приёмки."""

from codeteam.core.agent.answer_checks import AnswerContext
from codeteam.core.roles.acceptance.prompts import MISSING_FIX_PLAN_REMARK
from codeteam.core.roles.common import REWORK_VERDICT, check_verdict_file, read_verdict

# Файл плана доработки в черновике итоговой приёмки.
FIX_PLAN_FILE_NAME = "100_fix_plan.md"


def fix_plan_check(context: AnswerContext) -> str | None:
    """
    Проверка сдачи итоговой приёмки: при вердикте FIX в черновике есть план доработки.

        context: сдача работы итоговой приёмкой.

    Возвращает: Замечание или None, если вердикт PASS, вердикт не читается (его замечание даёт check_verdict_file)
        или план есть.
    """
    if check_verdict_file(context) is not None or read_verdict(remarks_dir = context.draft_dir):
        return None

    if (context.draft_dir / FIX_PLAN_FILE_NAME).is_file():
        return None

    return MISSING_FIX_PLAN_REMARK.format(rework_verdict = REWORK_VERDICT, plan_file = FIX_PLAN_FILE_NAME)
