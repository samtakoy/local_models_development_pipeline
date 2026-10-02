import tomllib
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.project import ProjectSettings


class ConfigError(ValueError):
    """Файл состава не собирается в прогон."""

def load_project_config(setup_dir: str) -> ProjectSettings:
    config_data = _read_toml(path = Path(setup_dir) / "set.toml")
    return ProjectSettings(
        path = config_data["project"],
        task = config_data["task"]["question"]
    )

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