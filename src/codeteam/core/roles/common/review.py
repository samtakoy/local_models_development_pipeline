"""Ревью работы роли: вердикт ревьюера, круги ревью, возврат работы роли, место ревьюера в графе."""

import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from langgraph.graph import StateGraph

from codeteam.core.pipeline.project import ReviewMode
from codeteam.core.pipeline.state import PipelineState, Review, Rework
from codeteam.core.roles.common.errors import PipelineError
from codeteam.core.roles.common.prompts import MISSING_VERDICT_REMARK, WRONG_VERDICT_REMARK

logger = logging.getLogger(__name__)

# Наибольшее число кругов ревью: ревью, исправление, повторное ревью.
REVIEW_ROUND_LIMIT = 2

# Папка внутри личной папки ревьюера: копия черновика, который ревьюер проверяет в этом запуске.
REVIEWED_DIR_NAME = "reviewed"

# Файл вердикта в черновике ревьюера: первая непустая строка содержит вердикт.
VERDICT_FILE_NAME = "000_verdict.md"

# Вердикт: работа принята.
ACCEPTED_VERDICT = "PASS"

# Вердикт: работа возвращается роли на доработку.
REWORK_VERDICT = "FIX"

# Слово вердикта в первой строке файла вердикта: отдельное слово, а не часть другого.
VERDICT_WORD_PATTERN = re.compile(rf"\b({re.escape(ACCEPTED_VERDICT)}|{re.escape(REWORK_VERDICT)})\b")

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


def rework_for(*, rework: Rework | None, role_name: str) -> Rework | None:
    """
    Выбирает возврат работы, адресованный роли.

        rework: возврат работы из состояния пайплайна.
        role_name: имя роли.

    Возвращает: Возврат работы, если он адресован этой роли; иначе None.
    """
    if rework is not None and rework.target == role_name:
        return rework

    return None


def make_rework(*, review: Review, remarks_dir: Path, preserve_draft: bool, preserve_context: bool) -> Rework | None:
    """
    Собирает возврат работы роли по ревью: только если работа не принята и круги ревью не кончились.
    Если круги кончились, а работа не принята, пишет предупреждение в лог.

        review: только что сделанное ревью.
        remarks_dir: папка черновика ревьюера: вердикт и замечания.
        preserve_draft: роль продолжит с черновиком из своей прошлой папки.
        preserve_context: роль продолжит с файлом контекста из своей прошлой папки.

    Возвращает: Возврат работы роли; None, если работа принята или круги кончились.
    """
    if review.accepted:
        return None

    if review.round >= REVIEW_ROUND_LIMIT:
        logger.warning(
            f"[ревью] работа роли {review.target} не принята за {REVIEW_ROUND_LIMIT} круга: {remarks_dir}; "
            f"пайплайн идёт дальше"
        )
        return None

    return Rework(
        target = review.target,
        remarks_dir = remarks_dir,
        preserve_draft = preserve_draft,
        preserve_context = preserve_context,
    )


def copy_reviewed_draft(*, draft_dir: Path, reviewer_dir: Path) -> Path:
    """
    Копирует проверяемый черновик в личную папку ревьюера: версия до исправления остаётся для сравнения.

        draft_dir: папка черновика роли, чью работу проверяет ревьюер.
        reviewer_dir: личная папка этого запуска ревьюера.

    Возвращает: Папку копии черновика.
    """
    reviewed_dir = reviewer_dir / REVIEWED_DIR_NAME
    if reviewed_dir.exists():
        shutil.rmtree(reviewed_dir)
    shutil.copytree(draft_dir, reviewed_dir)

    return reviewed_dir


def check_verdict_file(answer_dir: Path) -> str | None:
    """
    Проверка сдачи ревьюера: файл вердикта есть и его первая строка содержит ровно один вердикт.

        answer_dir: папка черновика ревьюера.

    Возвращает: Замечание ревьюеру или None, если вердикт читается.
    """
    verdict_path = answer_dir / VERDICT_FILE_NAME
    if not verdict_path.is_file():
        return MISSING_VERDICT_REMARK.format(
            verdict_file = VERDICT_FILE_NAME,
            accepted_verdict = ACCEPTED_VERDICT,
            rework_verdict = REWORK_VERDICT,
        )

    first_line = _verdict_line(verdict_path = verdict_path)
    if _verdict_word(line = first_line) is not None:
        return None

    return WRONG_VERDICT_REMARK.format(
        verdict_file = VERDICT_FILE_NAME,
        first_line = first_line,
        accepted_verdict = ACCEPTED_VERDICT,
        rework_verdict = REWORK_VERDICT,
    )


def read_verdict(*, remarks_dir: Path) -> bool:
    """
    Читает вердикт ревьюера из файла вердикта.

        remarks_dir: папка черновика ревьюера.

    Возвращает: True — работа принята, False — на доработку.
    """
    remark = check_verdict_file(remarks_dir)
    if remark is not None:
        raise PipelineError(f"черновик ревьюера {remarks_dir}: {remark}")

    first_line = _verdict_line(verdict_path = remarks_dir / VERDICT_FILE_NAME)

    return _verdict_word(line = first_line) == ACCEPTED_VERDICT


def _verdict_word(*, line: str) -> str | None:
    """
    Находит вердикт в строке.

        line: первая непустая строка файла вердикта.

    Возвращает: Слово вердикта; None, если в строке нет ни одного вердикта или есть оба.
    """
    words = set(VERDICT_WORD_PATTERN.findall(line))
    if len(words) != 1:
        return None

    return words.pop()


def _verdict_line(*, verdict_path: Path) -> str:
    """
    Берёт первую непустую строку файла вердикта без знаков заголовка markdown.

        verdict_path: файл вердикта.

    Возвращает: Первую непустую строку; пустую строку, если файл пустой.
    """
    lines = [line.strip().lstrip("#").strip() for line in verdict_path.read_text(encoding = "utf-8").splitlines()]

    return next((line for line in lines if line), "")


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
    работу роли — снова роль, иначе следующий шаг.

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
        if rework_for(rework = state["rework"], role_name = target) is not None:
            return target

        return next_route(state)

    workflow.add_node(review_name, review_node)
    workflow.add_edge(target, review_name)
    workflow.add_conditional_edges(review_name, route_after_review)
