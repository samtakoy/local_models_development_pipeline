"""Роль тестировщика: проверка готового приложения в браузере после последнего этапа."""

from codeteam.core.roles.tester.config import TESTER_ROLE
from codeteam.core.roles.tester.node import tester_node

__all__ = [
    "TESTER_ROLE",
    "tester_node",
]
