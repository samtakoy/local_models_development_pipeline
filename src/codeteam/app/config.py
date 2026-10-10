import tomllib
from pathlib import Path
from typing import Any

from codeteam.core.pipeline.graph import DEFAULT_ROLES
from codeteam.core.pipeline.project import ProjectSettings
from codeteam.core.roles.web_tester import WEB_TESTER_ROLE


class ConfigError(ValueError):
    """Файл состава не собирается в прогон."""

def load_project_config(setup_dir: str) -> ProjectSettings:
    config_data = _read_toml(path = Path(setup_dir) / "set.toml")
    pipeline_data = config_data.get("pipeline", {})
    roles = _parse_roles(pipeline_data = pipeline_data)
    browser_check = _parse_browser_check(pipeline_data = pipeline_data)
    if not browser_check and WEB_TESTER_ROLE.name in roles:
        raise ConfigError(
            f"[pipeline] browser_check = false, а роль {WEB_TESTER_ROLE.name} в списке ролей: "
            f"веб-тестировщику нужен браузер; уберите роль из roles или включите browser_check"
        )

    return ProjectSettings(
        path = config_data["project"],
        task = config_data["task"]["question"],
        roles = roles,
        browser_check = browser_check,
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

def _parse_browser_check(*, pipeline_data: dict[str, Any]) -> bool:
    """
    Читает обязательный признак проверки в браузере из раздела [pipeline] файла состава.

        pipeline_data: содержимое раздела [pipeline].

    Возвращает: Значение browser_check.
    """
    browser_check = pipeline_data.get("browser_check")
    if not isinstance(browser_check, bool):
        raise ConfigError(f"[pipeline] browser_check = {browser_check!r}: нужно true или false")

    return browser_check

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
