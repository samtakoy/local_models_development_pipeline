"""Роль веб-тестировщика: проверка готового приложения в браузере после последнего этапа."""

from codeteam.core.roles.web_tester.config import WEB_TESTER_ROLE
from codeteam.core.roles.web_tester.node import web_tester_node

__all__ = [
    "WEB_TESTER_ROLE",
    "web_tester_node",
]
