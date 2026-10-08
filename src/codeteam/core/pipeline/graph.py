"""Граф пайплайна: кто из агентов за кем идёт и что кому передаётся."""

import logging
from dataclasses import replace
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from codeteam.common.git import commit_all
from codeteam.core.pipeline.project import ReviewSettings
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.architect import ARCHITECT_ROLE, architect_node
from codeteam.core.roles.architect_review import ARCHITECT_REVIEW_ROLE, architect_review_node
from codeteam.core.roles.common import add_role_exit, parse_stage_number
from codeteam.core.roles.developer import DEVELOPER_ROLE, developer_node
from codeteam.core.roles.pm import PM_ROLE, pm_node
from codeteam.core.roles.researcher import RESEARCHER_ROLE, researcher_node
from codeteam.core.roles.senior import SENIOR_ROLE, senior_node

logger = logging.getLogger(__name__)

FINISH_STAGE_NODE_ID = "finish_stage"


def finish_stage_node(state: PipelineState, config: RunnableConfig):
    """Коммитит изменения проекта за текущий этап и переходит к следующему этапу."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    stages = state["stages"]
    stage_file = stages.current_file
    message = f"codeteam: этап {parse_stage_number(stage_file = stage_file)} — {_stage_title(stage_file = stage_file)}"
    if commit_all(project_dir = Path(cfg.project_path).resolve(), message = message):
        logger.info(f"[git] коммит: {message}")
    else:
        logger.warning(f"[git] этап {stage_file.name} не изменил проект, коммита нет")

    return {"stages": replace(stages, index = stages.index + 1, plan_dir = None)}


def route_next_stage(state: PipelineState) -> str:
    """
    Выбирает, куда идти после архитектора или после этапа.

        state: состояние пайплайна.

    Возвращает: Узел сеньора, если остались этапы; иначе END.
    """
    stages = state["stages"]
    if stages.index < len(stages.files):
        return SENIOR_ROLE.name

    return END


def create_pipeline_graph(*, review: ReviewSettings) -> CompiledStateGraph:
    """
    Собирает граф пайплайна: менеджер продукта, исследователь, архитектор, затем по каждому этапу
    сеньор, разработчик и коммит этапа. Ревьюеры встают после ролей, у которых ревью включено.

        review: режимы ревью ролей.

    Возвращает: Граф пайплайна.
    """
    workflow: StateGraph = StateGraph(PipelineState) # noqa

    workflow.add_node(PM_ROLE.name, pm_node)
    workflow.add_node(RESEARCHER_ROLE.name, researcher_node)
    workflow.add_node(ARCHITECT_ROLE.name, architect_node)
    workflow.add_node(SENIOR_ROLE.name, senior_node)
    workflow.add_node(DEVELOPER_ROLE.name, developer_node)
    workflow.add_node(FINISH_STAGE_NODE_ID, finish_stage_node)

    workflow.add_edge(START, PM_ROLE.name)
    workflow.add_edge(PM_ROLE.name, RESEARCHER_ROLE.name)
    workflow.add_edge(RESEARCHER_ROLE.name, ARCHITECT_ROLE.name)
    add_role_exit(
        workflow = workflow,
        mode = review.architect,
        target = ARCHITECT_ROLE.name,
        review_name = ARCHITECT_REVIEW_ROLE.name,
        review_node = architect_review_node,
        next_route = route_next_stage,
    )
    workflow.add_edge(SENIOR_ROLE.name, DEVELOPER_ROLE.name)
    workflow.add_edge(DEVELOPER_ROLE.name, FINISH_STAGE_NODE_ID)
    workflow.add_conditional_edges(FINISH_STAGE_NODE_ID, route_next_stage)

    return workflow.compile()


def _stage_title(*, stage_file: Path) -> str:
    """
    Берёт заголовок этапа: первую непустую строку файла этапа без знаков заголовка markdown.

        stage_file: файл этапа.

    Возвращает: Заголовок этапа; имя файла, если файл пустой.
    """
    for line in stage_file.read_text(encoding = "utf-8").splitlines():
        title = line.strip().lstrip("#").strip()
        if title:
            return title

    return stage_file.name
