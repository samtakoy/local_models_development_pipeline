"""Снимки состояния пайплайна: после каждой роли - коммит проекта и состояние рядом с журналом роли.
Снимок читается для продолжения прогона со следующей роли."""

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.state import PipelineState, Review, Rework, Stages

# Окончание имени файла снимка: <журнал роли>.state.json рядом с журналом.
STATE_FILE_SUFFIX = ".state.json"


def state_file_path(*, run_dir: Path, journal_name: str) -> Path:
    """
    Строит путь снимка состояния после роли.

        run_dir: папка прогона.
        journal_name: имя журнала роли без расширения.

    Возвращает: Файл <журнал роли>.state.json в папке прогона.
    """
    return run_dir / f"{journal_name}{STATE_FILE_SUFFIX}"


def save_state(*, state: PipelineState, commit: str, path: Path) -> None:
    """
    Записывает снимок в файл JSON: {"commit": коммит проекта, "state": состояние}. В состоянии пути - строками,
    этапы, ревью и возврат - словарями. Файл заменяется целиком, прерванная запись не портит прежний файл.

        state: состояние пайплайна.
        commit: коммит проекта на момент снимка.
        path: файл снимка.
    """
    plain_state = {key: asdict(value) if is_dataclass(value) else value for key, value in state.items()}
    snapshot = {"commit": commit, "state": plain_state}
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii = False, indent = 2, default = str), encoding = "utf-8")
    temporary_path.replace(path)


def load_state(*, path: Path) -> PipelineState:
    """
    Читает состояние пайплайна из снимка, записанного save_state.

        path: файл снимка.

    Возвращает: Состояние пайплайна.
    """
    data = json.loads(path.read_text(encoding = "utf-8"))["state"]

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
        # в снимках, записанных до появления полей, их нет
        tester_dir = _path_or_none(value = data.get("tester_dir")),
        web_scenarios_dir = _path_or_none(value = data.get("web_scenarios_dir")),
        web_tester_dir = _path_or_none(value = data.get("web_tester_dir")),
        web_scenarios_tester_dir = _path_or_none(value = data.get("web_scenarios_tester_dir")),
        acceptance_dir = _path_or_none(value = data.get("acceptance_dir")),
        next_role = data["next_role"],
        journal_name = data["journal_name"],
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
