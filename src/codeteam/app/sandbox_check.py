"""Проверка песочницы при запуске: без песочницы команды агентов идут только с согласия пользователя."""

from codeteam.common.shell.sandbox import is_sandbox_available
from codeteam.common.shell.sandbox.landlock_exec import MINIMAL_ABI_VERSION

# Вопрос пользователю, если песочница недоступна.
UNPROTECTED_RUN_QUESTION = (
    "Песочница недоступна (нужен macOS или Linux с Landlock версии {version} и новее): команды агентов "
    "пойдут без защиты файлов и процессов. Запускать без защиты? [y/N] "
)

# Ответы, которые считаются согласием.
CONSENT_ANSWERS = ("y", "yes", "д", "да")


def confirm_unprotected_run() -> None:
    """
    Если песочница недоступна, спрашивает согласие на запуск без защиты; без согласия завершает программу.
    """
    if is_sandbox_available():
        return

    try:
        answer = input(UNPROTECTED_RUN_QUESTION.format(version = MINIMAL_ABI_VERSION))
    except EOFError:
        answer = ""

    if answer.strip().lower() not in CONSENT_ANSWERS:
        raise SystemExit("запуск отменён: песочница недоступна")
