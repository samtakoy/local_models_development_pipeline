"""Файл состояния пайплайна: запись после каждой роли и чтение для продолжения прогона с прерванной роли."""

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.state import PipelineState, Review, Rework, Stages

# Файл состояния в папке прогона.
STATE_FILE_NAME = "state.json"


def save_state(*, state: PipelineState, path: Path) -> None:
    """
    Записывает состояние пайплайна в файл JSON: пути - строками, этапы, ревью и возврат - словарями.
    Файл заменяется целиком, прерванная запись не портит прежний файл.

        state: состояние пайплайна.
        path: файл состояния.
    """
    plain = {key: asdict(value) if is_dataclass(value) else value for key, value in state.items()}
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(json.dumps(plain, ensure_ascii = False, indent = 2, default = str), encoding = "utf-8")
    temporary_path.replace(path)


def load_state(*, path: Path) -> PipelineState:
    """
    Читает состояние пайплайна из файла JSON, записанного save_state.

        path: файл состояния.

    Возвращает: Состояние пайплайна.
    """
    data = json.loads(path.read_text(encoding = "utf-8"))

    return PipelineState(
        task = data["task"],
        requirements_dir = _path_or_none(value = data["requirements_dir"]),
        requirements_file = _path_or_none(value = data["requirements_file"]),
        research_dir = _path_or_none(value = data["research_dir"]),
        plan_dir = _path_or_none(value = data["plan_dir"]),
        architecture_file = _path_or_none(value = data["architecture_file"]),
        stages = _stages_or_none(value = data["stages"]),
        review = None if data["review"] is None else Review(**data["review"]),
        rework = _rework_or_none(value = data["rework"]),
        next_role = data["next_role"],
        journal_count = data["journal_count"],
    )


def _path_or_none(*, value: str | None) -> Path | None:
    """
    Переводит строку пути в путь.

        value: путь строкой или None.

    Возвращает: Путь; None, если значения нет.
    """
    if value is None:
        return None

    return Path(value)


def _stages_or_none(*, value: dict[str, Any] | None) -> Stages | None:
    """
    Собирает этапы из словаря.

        value: словарь полей Stages или None.

    Возвращает: Этапы; None, если значения нет.
    """
    if value is None:
        return None

    return Stages(
        files = tuple(Path(file) for file in value["files"]),
        started = value["started"],
        plan_dir = _path_or_none(value = value["plan_dir"]),
        fix_rounds = value["fix_rounds"],
    )


def _rework_or_none(*, value: dict[str, Any] | None) -> Rework | None:
    """
    Собирает возврат работы из словаря.

        value: словарь полей Rework или None.

    Возвращает: Возврат работы; None, если значения нет.
    """
    if value is None:
        return None

    return Rework(
        target = value["target"],
        remarks_dir = Path(value["remarks_dir"]),
        preserve_draft = value["preserve_draft"],
        preserve_context = value["preserve_context"],
    )
