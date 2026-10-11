"""Имя папки прогона: время запуска и модель агентов."""

import re
from datetime import datetime

# Формат времени запуска в имени папки прогона.
RUN_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"


def make_run_dir_name(*, model_name: str) -> str:
    """
    Составляет имя папки прогона из текущего времени и имени модели без знаков, кроме букв и цифр.

        model_name: модель агентов, например gemma4:e4b-it-qat.

    Возвращает: Имя <дата_время>-<модель>, например 2026-10-11_01-44-23-gemma4e4bitqat.
    """
    model_part = re.sub(r"[\W_]", "", model_name)

    return f"{datetime.now().strftime(RUN_TIME_FORMAT)}-{model_part}"
