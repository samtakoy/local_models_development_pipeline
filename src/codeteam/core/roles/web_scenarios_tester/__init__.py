"""Проверка по сценариям в браузере: прогон сценариев составителя через помощника с браузером и вердикт оценщика."""

from codeteam.core.roles.web_scenarios_tester.config import WEB_SCENARIOS_TESTER_ROLE
from codeteam.core.roles.web_scenarios_tester.node import web_scenarios_tester_node

__all__ = [
    "WEB_SCENARIOS_TESTER_ROLE",
    "web_scenarios_tester_node",
]
