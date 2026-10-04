"""Граф пайплайна: кто из агентов за кем идёт и что кому передаётся."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from codeteam.app.settings import Settings
from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.run_agent import run_agent
from codeteam.core.pipeline.prompts import ARCHITECT_TASK, RESEARCHER_TASK
from codeteam.core.roles import load_role_prompt

PIPELINE_CFG_NAME = "pipeline"

RESEARCHER_NODE_ID = "researcher"
ARCHITECT_NODE_ID = "architect"


class PipelineState(TypedDict):
    """
    Состояние пайплайна.

        task: задача пользователя.
        research_dir: папка черновика исследователя; None, пока он не отработал.
        plan_dir: папка черновика архитектора: файлы этапов; None, пока он не отработал.
    """

    task: str
    research_dir: Path | None
    plan_dir: Path | None


@dataclass(frozen = True)
class PipelineConfig:
    """
    Настройки запуска пайплайна.

        project_path: папка рабочего проекта.
        run_dir: папка прогона: журналы агентов.
        model_name: модель агентов.
        settings: настройки приложения.
    """

    project_path: str
    run_dir: Path
    model_name: str
    settings: Settings


def researcher_node(state: PipelineState, config: RunnableConfig):
    """Запускает исследователя кода на задаче пользователя."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    task = RESEARCHER_TASK.format(task = state["task"])
    research_dir = _run_role(cfg = cfg, name = RESEARCHER_NODE_ID, number = 1, task = task, input_dirs = ())

    return {"research_dir": research_dir}


def architect_node(state: PipelineState, config: RunnableConfig):
    """Запускает архитектора: по задаче и отчёту исследователя он делит работу на этапы."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    research_dir = state["research_dir"]
    task = ARCHITECT_TASK.format(
        task = state["task"],
        research_dir = research_dir.relative_to(Path(cfg.project_path).resolve()),
    )
    plan_dir = _run_role(
        cfg = cfg,
        name = ARCHITECT_NODE_ID,
        number = 2,
        task = task,
        input_dirs = (research_dir,)
    )

    return {"plan_dir": plan_dir}


def create_pipeline_graph() -> CompiledStateGraph:
    """
    Собирает граф пайплайна: исследователь, затем архитектор.

    Возвращает: Граф пайплайна.
    """
    workflow: StateGraph = StateGraph(PipelineState) # noqa

    workflow.add_node(RESEARCHER_NODE_ID, researcher_node)
    workflow.add_node(ARCHITECT_NODE_ID, architect_node)

    workflow.add_edge(START, RESEARCHER_NODE_ID)
    workflow.add_edge(RESEARCHER_NODE_ID, ARCHITECT_NODE_ID)
    workflow.add_edge(ARCHITECT_NODE_ID, END)

    return workflow.compile()


def _run_role(
    *,
    cfg: PipelineConfig,
    name: str,
    number: int,
    task: str,
    input_dirs: tuple[Path, ...],
) -> Path:
    """
    Запускает агента роли и ждёт его результата.

        cfg: настройки запуска пайплайна.
        name: имя роли; по нему берётся промпт роли.
        number: номер агента в прогоне для имени журнала.
        task: задача агенту.
        input_dirs: папки результатов других агентов.

    Возвращает: Папку черновика агента.
    """
    role = AgentRole(
        name = name,
        system_prompt = load_role_prompt(name = name),
        model_name = cfg.model_name
    )

    return run_agent(
        role = role,
        task = task,
        input_dirs = input_dirs,
        project_path = cfg.project_path,
        journal_path = cfg.run_dir / f"{number:02d}_{name}.md",
        settings = cfg.settings,
    )
