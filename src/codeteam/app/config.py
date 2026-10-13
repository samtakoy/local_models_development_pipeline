import tomllib
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.graph import DEFAULT_ROLES
from codeteam.core.pipeline.project import ProjectSettings
from codeteam.core.roles.web_scenarios_tester import WEB_SCENARIOS_TESTER_ROLE
from codeteam.core.roles.web_tester import WEB_TESTER_ROLE


# Папка начального содержимого проекта в папке задачи, рядом с set.toml.
START_DIR_NAME = "start_folder"


class ConfigError(ValueError):
    """Файл состава не собирается в прогон."""

def load_project_config(*, setup_dir: str, workspaces_dir: Path) -> ProjectSettings:
    """
    Читает файл состава set.toml из папки задачи.

        setup_dir: папка задачи с файлом set.toml.
        workspaces_dir: папка рабочих проектов: от неё считается относительный путь проекта.

    Возвращает: Проект и задачу прогона; путь проекта полный.
    """
    config_data = _read_toml(path = Path(setup_dir) / "set.toml")
    pipeline_data = config_data.get("pipeline", {})
    roles = _parse_roles(pipeline_data = pipeline_data)
    browser_check = _parse_required_flag(pipeline_data = pipeline_data, name = "browser_check")
    library_docs = _parse_required_flag(pipeline_data = pipeline_data, name = "library_docs")
    browser_roles = [name for name in (WEB_TESTER_ROLE.name, WEB_SCENARIOS_TESTER_ROLE.name) if name in roles]
    if not browser_check and browser_roles:
        raise ConfigError(
            f"[pipeline] browser_check = false, а роли {', '.join(browser_roles)} в списке ролей: "
            f"им нужен браузер; уберите роли из roles или включите browser_check"
        )

    return ProjectSettings(
        path = str(workspaces_dir / config_data["project"]),
        start_dir = Path(setup_dir) / START_DIR_NAME,
        task = config_data["task"]["question"],
        roles = roles,
        browser_check = browser_check,
        library_docs = library_docs,
    )

def _parse_roles(*, pipeline_data: dict[str, Any]) -> tuple[str, ...]:
    """
    Читает последовательность ролей из раздела [pipeline] файла состава.

        pipeline_data: содержимое раздела [pipeline].

    Возвращает: Роли из списка roles; без списка - DEFAULT_ROLES, полный пайплайн.
    """
    roles = pipeline_data.get("roles")
    if roles is None:
        return DEFAULT_ROLES

    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ConfigError(f"[pipeline] roles = {roles!r}: нужен список имён ролей")

    return tuple(roles)

def _parse_required_flag(*, pipeline_data: dict[str, Any], name: str) -> bool:
    """
    Читает обязательный признак из раздела [pipeline] файла состава.

        pipeline_data: содержимое раздела [pipeline].
        name: имя признака: browser_check или library_docs.

    Возвращает: Значение признака.
    """
    value = pipeline_data.get(name)
    if not isinstance(value, bool):
        raise ConfigError(f"[pipeline] {name} = {value!r}: нужно true или false")

    return value

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
