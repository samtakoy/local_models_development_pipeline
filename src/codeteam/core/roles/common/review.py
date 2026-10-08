"""Ревью работы роли: вердикт ревьюера, круги ревью, место ревьюера в графе."""

import logging
from collections.abc import Callable
from pathlib import Path

from langgraph.graph import StateGraph

from codeteam.core.pipeline.project import ReviewMode
from codeteam.core.pipeline.state import PipelineState, Review
from codeteam.core.roles.common.errors import PipelineError

logger = logging.getLogger(__name__)

# Наибольшее число кругов ревью: ревью, исправление, повторное ревью.
REVIEW_ROUND_LIMIT = 2

# Файл вердикта в черновике ревьюера: первая непустая строка — вердикт.
VERDICT_FILE_NAME = "000_verdict.md"

# Вердикт: работа принята.
ACCEPTED_VERDICT = "PASS"

# Вердикт: работа возвращается роли на доработку.
REWORK_VERDICT = "FIX"

# Выбор следующего узла графа по состоянию пайплайна.
Route = Callable[[PipelineState], str]

# Узел графа пайплайна.
PipelineNode = Callable[..., dict]


def next_review_round(*, review: Review | None, target: str) -> int:
    """
    Считает номер следующего круга ревью роли.

        review: последнее ревью из состояния.
        target: имя роли, чью работу проверяет ревьюер.

    Возвращает: Номер круга, с 1.
    """
    if review is not None and review.target == target:
        return review.round + 1

    return 1


def needs_fix(*, review: Review | None, target: str) -> bool:
    """
    Проверяет, вернул ли ревьюер работу роли на доработку.

        review: последнее ревью из состояния.
        target: имя роли.

    Возвращает: True, если последнее ревью — работы этой роли и с вердиктом «доработать».
    """
    return review is not None and review.target == target and not review.accepted


def read_verdict(*, remarks_dir: Path) -> bool:
    """
    Читает вердикт ревьюера из файла вердикта.

        remarks_dir: папка черновика ревьюера.

    Возвращает: True — работа принята, False — на доработку.
    """
    verdict_path = remarks_dir / VERDICT_FILE_NAME
    if not verdict_path.is_file():
        # TODO падать нельзя надо хинт (user message) агенту
        raise PipelineError(f"в черновике ревьюера {remarks_dir} нет файла {VERDICT_FILE_NAME}")

    lines = [line.strip().lstrip("#").strip() for line in verdict_path.read_text(encoding = "utf-8").splitlines()]
    verdict = next((line for line in lines if line), "")
    if verdict == ACCEPTED_VERDICT:
        return True
    if verdict == REWORK_VERDICT:
        return False

    raise PipelineError(
        f"в {verdict_path} первая строка {verdict!r}: ожидается {ACCEPTED_VERDICT} или {REWORK_VERDICT}"
    )


def check_review_limit(*, review: Review, mode: ReviewMode) -> None:
    """
    Проверяет последний круг ревью: работа не принята и кругов больше нет.

    В режиме STRICT останавливает прогон, в режиме ON пишет предупреждение.

        review: только что сделанное ревью.
        mode: режим ревью роли.
    """
    if review.accepted or review.round < REVIEW_ROUND_LIMIT:
        return

    message = f"[ревью] работа роли {review.target} не принята за {REVIEW_ROUND_LIMIT} круга: {review.remarks_dir}"
    if mode == ReviewMode.STRICT:
        raise PipelineError(message)

    logger.warning(f"{message}; пайплайн идёт дальше")


def add_role_exit(
    *,
    workflow: StateGraph,
    mode: ReviewMode,
    target: str,
    review_name: str,
    review_node: PipelineNode,
    next_route: Route,
) -> None:
    """
    Соединяет роль со следующим шагом графа: напрямую или через ревьюера.

    Без ревью после роли сразу выбирается следующий шаг. С ревью после роли идёт ревьюер; если он вернул
    работу на доработку и круги не кончились — снова роль, иначе следующий шаг.

        workflow: граф пайплайна.
        mode: режим ревью роли.
        target: имя узла роли.
        review_name: имя узла ревьюера.
        review_node: узел ревьюера.
        next_route: выбор следующего шага после роли.
    """
    if mode == ReviewMode.OFF:
        workflow.add_conditional_edges(target, next_route)
        return

    def route_after_review(state: PipelineState) -> str:
        """Возвращает работу роли на доработку или выбирает следующий шаг."""
        review = state["review"]
        if not review.accepted and review.round < REVIEW_ROUND_LIMIT:
            return target

        return next_route(state)

    workflow.add_node(review_name, review_node)
    workflow.add_edge(target, review_name)
    workflow.add_conditional_edges(review_name, route_after_review)
