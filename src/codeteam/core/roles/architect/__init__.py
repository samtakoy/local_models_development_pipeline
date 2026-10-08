"""Роль архитектора: общее решение задачи и деление работы на этапы."""

from codeteam.core.roles.architect.config import ARCHITECT_ROLE, ARCHITECTURE_FILE_NAME
from codeteam.core.roles.architect.node import architect_node

__all__ = [
    "ARCHITECTURE_FILE_NAME",
    "ARCHITECT_ROLE",
    "architect_node",
]
