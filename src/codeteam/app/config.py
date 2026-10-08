import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.project import ProjectSettings, ReviewMode, ReviewSettings


class ConfigError(ValueError):
    """Файл состава не собирается в прогон."""

def load_project_config(setup_dir: str) -> ProjectSettings:
    config_data = _read_toml(path = Path(setup_dir) / "set.toml")
    return ProjectSettings(
        path = config_data["project"],
        task = config_data["task"]["question"],
        review = _parse_review(review_data = config_data.get("review", {})),
    )

def _parse_review(*, review_data: dict[str, Any]) -> ReviewSettings:
    """
    Собирает режимы ревью ролей из раздела [review] файла состава.

        review_data: содержимое раздела [review]: имя роли → режим.

    Возвращает: Режимы ревью; у ролей без записи в разделе — ReviewMode.OFF.
    """
    role_names = [field.name for field in fields(ReviewSettings)]
    unknown_names = sorted(set(review_data) - set(role_names))
    if unknown_names:
        raise ConfigError(f"[review]: у ролей {', '.join(unknown_names)} нет ревьюера; есть у: {', '.join(role_names)}")

    modes = {}
    for role_name in role_names:
        value = review_data.get(role_name, ReviewMode.OFF.value)
        try:
            modes[role_name] = ReviewMode(value)
        except ValueError as error:
            allowed = ", ".join(mode.value for mode in ReviewMode)
            raise ConfigError(f"[review] {role_name} = {value!r}: допустимо {allowed}") from error

    return ReviewSettings(**modes)

def _read_toml(*, path: Path) -> dict[str, Any]:
    """
    Читает файл TOML.

        path: файл.

    Возвращает: Содержимое файла.
    """
    try:
        return tomllib.loads(path.read_text(encoding = "utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"файл {path}: {error}") from error
