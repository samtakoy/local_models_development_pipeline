"""Роль менеджера продукта: чеклист требований заказчика по тексту задачи."""

from codeteam.core.roles.pm.config import PM_ROLE, REQUIREMENTS_FILE_NAME
from codeteam.core.roles.pm.node import pm_node

__all__ = [
    "PM_ROLE",
    "REQUIREMENTS_FILE_NAME",
    "pm_node",
]
