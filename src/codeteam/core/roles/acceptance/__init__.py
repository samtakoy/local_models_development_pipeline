"""Роль итоговой приёмки: итоговый вердикт по отчётам тестировщиков и план доработки."""

from codeteam.core.roles.acceptance.config import ACCEPTANCE_ROLE
from codeteam.core.roles.acceptance.node import acceptance_node

__all__ = [
    "ACCEPTANCE_ROLE",
    "acceptance_node",
]
