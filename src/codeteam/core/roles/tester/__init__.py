"""Роль тестировщика: проверка готового приложения после последнего этапа любым подходящим способом,
в браузере — через помощника."""

from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.tester.node import tester_node

__all__ = [
    "TESTER_ROLE",
    "tester_node",
]
