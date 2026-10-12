"""Роль итоговой приёмки: итоговый вердикт по отчётам тестировщиков и план доработки."""

from codeteam.core.roles.acceptance.config import ACCEPTANCE_ROLE
from codeteam.core.roles.acceptance.node import acceptance_node
from codeteam.core.roles.acceptance.report import write_acceptance_report

__all__ = [
    "ACCEPTANCE_ROLE",
    "acceptance_node",
    "write_acceptance_report",
]
