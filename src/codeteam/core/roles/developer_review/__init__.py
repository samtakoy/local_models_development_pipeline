"""Роль приёмщика этапа: проверка этапа в запущенном приложении, вердикт и замечания разработчику."""

from codeteam.core.roles.developer_review.config import DEVELOPER_REVIEW_ROLE
from codeteam.core.roles.developer_review.node import developer_review_node

__all__ = [
    "DEVELOPER_REVIEW_ROLE",
    "developer_review_node",
]
