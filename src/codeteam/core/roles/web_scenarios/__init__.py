"""Роль составителя сценариев: файл запуска приложения и сценарии проверки в браузере."""

from codeteam.core.roles.web_scenarios.config import WEB_SCENARIOS_ROLE
from codeteam.core.roles.web_scenarios.launch import AppLaunch, LaunchFileError, read_app_launch, scenario_files
from codeteam.core.roles.web_scenarios.node import web_scenarios_node

__all__ = [
    "AppLaunch",
    "LaunchFileError",
    "WEB_SCENARIOS_ROLE",
    "read_app_launch",
    "scenario_files",
    "web_scenarios_node",
]
