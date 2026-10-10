"""Граф пайплайна: один узел запускает роли по списку, следующая роль выбирается по состоянию после роли."""

from collections.abc import Callable

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.architect import ARCHITECT_ROLE, architect_node
from codeteam.core.roles.architect_review import ARCHITECT_REVIEW_ROLE, architect_review_node
from codeteam.core.roles.common import PipelineError
from codeteam.core.roles.developer import DEVELOPER_ROLE, developer_node
from codeteam.core.roles.developer_review import DEVELOPER_REVIEW_ROLE, developer_review_node
from codeteam.core.roles.pm import PM_ROLE, pm_node
from codeteam.core.roles.researcher import RESEARCHER_ROLE, researcher_node
from codeteam.core.roles.senior import SENIOR_ROLE, senior_node
from codeteam.core.roles.web_tester import WEB_TESTER_ROLE, web_tester_node

# Узел графа, который запускает роль из next_role.
ROLE_NODE_ID = "role"

# Узлы ролей по именам ролей: узел запускает агента роли и возвращает обновление состояния.
ROLE_NODES: dict[str, Callable[[PipelineState, RunnableConfig], dict]] = {
    PM_ROLE.name: pm_node,
    RESEARCHER_ROLE.name: researcher_node,
    ARCHITECT_ROLE.name: architect_node,
    ARCHITECT_REVIEW_ROLE.name: architect_review_node,
    SENIOR_ROLE.name: senior_node,
    DEVELOPER_ROLE.name: developer_node,
    DEVELOPER_REVIEW_ROLE.name: developer_review_node,
    WEB_TESTER_ROLE.name: web_tester_node,
}

# Роли этапа: в списке ролей идут подряд и повторяются для каждого этапа плана архитектора.
STAGE_ROLE_NAMES = (SENIOR_ROLE.name, DEVELOPER_ROLE.name, DEVELOPER_REVIEW_ROLE.name)

# Последовательность ролей, если файл состава её не задаёт: полный пайплайн.
DEFAULT_ROLES = (
    PM_ROLE.name,
    RESEARCHER_ROLE.name,
    ARCHITECT_ROLE.name,
    ARCHITECT_REVIEW_ROLE.name,
    SENIOR_ROLE.name,
    DEVELOPER_ROLE.name,
    DEVELOPER_REVIEW_ROLE.name,
    WEB_TESTER_ROLE.name,
)


def create_pipeline_graph(*, roles: tuple[str, ...]) -> CompiledStateGraph:
    """
    Проверяет последовательность ролей и собирает граф пайплайна: один узел запускает роль из next_role
    и вызывается снова, пока следующая роль есть.

        roles: последовательность ролей пайплайна.

    Возвращает: Граф пайплайна.
    """
    check_roles(roles = roles)
    workflow: StateGraph = StateGraph(PipelineState) # noqa
    workflow.add_node(ROLE_NODE_ID, role_node)
    workflow.add_edge(START, ROLE_NODE_ID)
    workflow.add_conditional_edges(ROLE_NODE_ID, route_after_role)

    return workflow.compile()


def check_roles(*, roles: tuple[str, ...]) -> None:
    """
    Проверяет последовательность ролей: список не пуст, имена известны и не повторяются, роли этапа идут подряд.
    Ошибку поднимает PipelineError.

        roles: последовательность ролей пайплайна.
    """
    if not roles:
        raise PipelineError("список ролей пайплайна пуст")

    unknown = [role for role in roles if role not in ROLE_NODES]
    if unknown:
        raise PipelineError(f"неизвестные роли: {', '.join(unknown)}; есть роли: {', '.join(ROLE_NODES)}")

    repeated = sorted({role for role in roles if roles.count(role) > 1})
    if repeated:
        raise PipelineError(f"роли повторяются в списке: {', '.join(repeated)}")

    stage_positions = _stage_positions(roles = roles)
    if stage_positions and stage_positions != list(range(stage_positions[0], stage_positions[-1] + 1)):
        raise PipelineError(f"роли этапа {', '.join(STAGE_ROLE_NAMES)} должны идти в списке подряд")


def role_node(state: PipelineState, config: RunnableConfig) -> dict:
    """
    Запускает роль из next_role и выбирает следующую роль по состоянию после неё.

        state: состояние пайплайна.
        config: настройки запуска графа с настройками пайплайна.

    Возвращает: Обновление состояния от роли и следующая роль.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    current = state["next_role"]
    update = ROLE_NODES[current](state, config)
    next_role = choose_next_role(roles = cfg.roles, current = current, state = {**state, **update})

    return {**update, "next_role": next_role}


def route_after_role(state: PipelineState) -> str:
    """
    Ведёт к следующей роли или к концу пайплайна.

        state: состояние пайплайна.

    Возвращает: Узел ролей, если следующая роль есть; иначе END.
    """
    if state["next_role"] is None:
        return END

    return ROLE_NODE_ID


def choose_next_role(*, roles: tuple[str, ...], current: str, state: PipelineState) -> str | None:
    """
    Выбирает роль после текущей.

    Возврат работы ведёт к ближайшей роли-цели перед текущей. Если следующая по списку роль стоит после ролей
    этапа или список кончился, а неначатые этапы есть, - к первой роли этапа. Иначе - следующая по списку.

        roles: последовательность ролей пайплайна.
        current: роль, которая только что отработала.
        state: состояние пайплайна после неё.

    Возвращает: Имя следующей роли; None, если пайплайн закончен.
    """
    position = roles.index(current)
    rework = state["rework"]
    if rework is not None:
        return _nearest_before(roles = roles, position = position, role_name = rework.target)

    following = roles[position + 1] if position + 1 < len(roles) else None
    stages = state["stages"]
    if stages is not None and stages.has_unstarted and _is_after_stage_roles(roles = roles, role_name = following):
        return roles[_stage_positions(roles = roles)[0]]

    return following


def _nearest_before(*, roles: tuple[str, ...], position: int, role_name: str) -> str:
    """
    Находит роль с именем role_name перед позицией в списке, ближайшую к ней.
    Ошибку поднимает PipelineError, если такой роли перед позицией нет.

        roles: последовательность ролей пайплайна.
        position: позиция текущей роли.
        role_name: имя искомой роли.

    Возвращает: Имя найденной роли.
    """
    for candidate in reversed(roles[:position]):
        if candidate == role_name:
            return candidate

    raise PipelineError(f"работа возвращена роли {role_name}, но её нет в списке перед ролью {roles[position]}")


def _stage_positions(*, roles: tuple[str, ...]) -> list[int]:
    """
    Находит позиции ролей этапа в списке.

        roles: последовательность ролей пайплайна.

    Возвращает: Позиции ролей этапа по возрастанию; пустой список, если ролей этапа нет.
    """
    return [position for position, role in enumerate(roles) if role in STAGE_ROLE_NAMES]


def _is_after_stage_roles(*, roles: tuple[str, ...], role_name: str | None) -> bool:
    """
    Проверяет, что роль стоит в списке после ролей этапа.

        roles: последовательность ролей пайплайна.
        role_name: имя роли; None - конец списка.

    Возвращает: True для конца списка и для роли после ролей этапа; False, если ролей этапа в списке нет.
    """
    stage_positions = _stage_positions(roles = roles)
    if not stage_positions:
        return False

    if role_name is None:
        return True

    return roles.index(role_name) > stage_positions[-1]
