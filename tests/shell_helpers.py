"""Общие действия тестов команд оболочки: проверка и ожидание процессов."""

import os
import time

# Сколько ждать исчезновения снятого процесса, секунды.
PROCESS_GONE_TIMEOUT_SECONDS = 5

# Пауза между проверками процесса, секунды.
PROCESS_POLL_SECONDS = 0.05


def is_process_alive(*, process_id: int) -> bool:
    """
    Проверяет, работает ли процесс.

        process_id: номер процесса.

    Возвращает: True, если процесс есть.
    """
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False

    return True


def wait_process_gone(*, process_id: int) -> bool:
    """
    Ждёт исчезновения процесса не дольше PROCESS_GONE_TIMEOUT_SECONDS.

        process_id: номер процесса.

    Возвращает: True, если процесс исчез.
    """
    deadline = time.monotonic() + PROCESS_GONE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not is_process_alive(process_id = process_id):
            return True
        time.sleep(PROCESS_POLL_SECONDS)

    return False


def wait_process_group_gone(*, process_group_id: int) -> bool:
    """
    Ждёт исчезновения всех процессов группы не дольше PROCESS_GONE_TIMEOUT_SECONDS.

        process_group_id: номер группы процессов.

    Возвращает: True, если в группе не осталось процессов.
    """
    deadline = time.monotonic() + PROCESS_GONE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return True
        time.sleep(PROCESS_POLL_SECONDS)

    return False
