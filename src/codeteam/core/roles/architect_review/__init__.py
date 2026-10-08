"""Роль ревьюера архитектора: вердикт и замечания к решению и этапам архитектора."""

from codeteam.core.roles.architect_review.config import ARCHITECT_REVIEW_ROLE
from codeteam.core.roles.architect_review.node import architect_review_node

__all__ = [
    "ARCHITECT_REVIEW_ROLE",
    "architect_review_node",
]
