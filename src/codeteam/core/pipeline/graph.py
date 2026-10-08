"""Граф пайплайна: кто из агентов за кем идёт и что кому передаётся."""

import logging
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from codeteam.common.git import commit_all
from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.step_hooks import StepHook
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.pipeline.prompts import DEVELOPER_TASK, PM_TASK, RESEARCHER_TASK
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles import ROLES_DIR
from codeteam.core.roles.architect import ARCHITECT_ROLE, architect_node
from codeteam.core.roles.common import DRAFT_TOOL_NAMES, PROJECT_TOOL_NAMES, REQUIREMENTS_FILE_NAME, PipelineError, \
    RoleSettings, build_stage_dir_name, make_journal_name, parse_stage_number, run_role
from codeteam.core.roles.senior import SENIOR_ROLE, senior_node

logger = logging.getLogger(__name__)

PM_NODE_ID = "pm"
RESEARCHER_NODE_ID = "researcher"
DEVELOPER_NODE_ID = "developer"
FINISH_STAGE_NODE_ID = "finish_stage"


def pm_node(state: PipelineState, config: RunnableConfig):
    """Запускает менеджера продукта: по тексту задачи пользователя он пишет чеклист требований без доступа к проекту."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    requirements_dir = _run_role(
        cfg = cfg,
        name = PM_NODE_ID,
        journal_name = make_journal_name(journal_count = state["journal_count"], label = PM_NODE_ID),
        prompt_fields = {"requirements_file": REQUIREMENTS_FILE_NAME},
        reasoning_level = ReasoningLevel.HIGH,
        task = PM_TASK.format(task = state["task"]),
        input_dirs = (),
        private_dir_name = Path(PM_NODE_ID),
        tool_names = DRAFT_TOOL_NAMES,
        step_hooks = (),
        extra_readable_dirs = (),
        extra_writable_dirs = (),
    )
    if not (requirements_dir / REQUIREMENTS_FILE_NAME).is_file():
        raise PipelineError(f"в черновике менеджера продукта {requirements_dir} нет файла {REQUIREMENTS_FILE_NAME}")

    return {"requirements_dir": requirements_dir, "journal_count": state["journal_count"] + 1}


def researcher_node(state: PipelineState, config: RunnableConfig):
    """Запускает исследователя кода на задаче пользователя."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    task = RESEARCHER_TASK.format(task = state["task"])
    research_dir = _run_role(
        cfg = cfg,
        name = RESEARCHER_NODE_ID,
        journal_name = make_journal_name(journal_count = state["journal_count"], label = RESEARCHER_NODE_ID),
        prompt_fields = {},
        reasoning_level = ReasoningLevel.LOW,
        task = task,
        input_dirs = (),
        private_dir_name = Path(RESEARCHER_NODE_ID),
        tool_names = PROJECT_TOOL_NAMES,
        step_hooks = (),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
    )

    return {"research_dir": research_dir, "journal_count": state["journal_count"] + 1}


def developer_node(state: PipelineState, config: RunnableConfig):
    """Запускает разработчика текущего этапа: по плану сеньора он пишет код этапа в папке проекта."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stage_index = state["stage_index"]
    stage_dir_name = build_stage_dir_name(stage_file = state["stage_files"][stage_index])
    stage_plan_dir = state["stage_plan_dir"]
    _run_role(
        cfg = cfg,
        name = DEVELOPER_NODE_ID,
        journal_name = make_journal_name(
            journal_count = state["journal_count"],
            label = f"{stage_dir_name}_{DEVELOPER_NODE_ID}",
        ),
        prompt_fields = {"check_dir": CHECK_DIR.as_posix()},
        reasoning_level = ReasoningLevel.LOW,
        task = DEVELOPER_TASK.format(stage_plan_dir = stage_plan_dir.relative_to(project_dir)),
        input_dirs = (stage_plan_dir,),
        private_dir_name = stage_dir_name / DEVELOPER_NODE_ID,
        tool_names = PROJECT_TOOL_NAMES,
        step_hooks = (),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (project_dir,),
    )

    return {"journal_count": state["journal_count"] + 1}


def finish_stage_node(state: PipelineState, config: RunnableConfig):
    """Коммитит изменения проекта за текущий этап и переходит к следующему этапу."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    stage_file = state["stage_files"][state["stage_index"]]
    message = f"codeteam: этап {parse_stage_number(stage_file = stage_file)} — {_stage_title(stage_file = stage_file)}"
    if commit_all(project_dir = Path(cfg.project_path).resolve(), message = message):
        logger.info(f"[git] коммит: {message}")
    else:
        logger.warning(f"[git] этап {stage_file.name} не изменил проект, коммита нет")

    return {"stage_index": state["stage_index"] + 1, "stage_plan_dir": None}


def route_next_stage(state: PipelineState) -> str:
    """
    Выбирает, куда идти после архитектора или после этапа.

        state: состояние пайплайна.

    Возвращает: Узел сеньора, если остались этапы; иначе END.
    """
    if state["stage_index"] < len(state["stage_files"]):
        return SENIOR_ROLE.name

    return END


def create_pipeline_graph() -> CompiledStateGraph:
    """
    Собирает граф пайплайна: менеджер продукта, исследователь, архитектор, затем по каждому этапу
    сеньор, разработчик и коммит этапа.

    Возвращает: Граф пайплайна.
    """
    workflow: StateGraph = StateGraph(PipelineState) # noqa

    workflow.add_node(PM_NODE_ID, pm_node)
    workflow.add_node(RESEARCHER_NODE_ID, researcher_node)
    workflow.add_node(ARCHITECT_ROLE.name, architect_node)
    workflow.add_node(SENIOR_ROLE.name, senior_node)
    workflow.add_node(DEVELOPER_NODE_ID, developer_node)
    workflow.add_node(FINISH_STAGE_NODE_ID, finish_stage_node)

    workflow.add_edge(START, PM_NODE_ID)
    workflow.add_edge(PM_NODE_ID, RESEARCHER_NODE_ID)
    workflow.add_edge(RESEARCHER_NODE_ID, ARCHITECT_ROLE.name)
    workflow.add_conditional_edges(ARCHITECT_ROLE.name, route_next_stage)
    workflow.add_edge(SENIOR_ROLE.name, DEVELOPER_NODE_ID)
    workflow.add_edge(DEVELOPER_NODE_ID, FINISH_STAGE_NODE_ID)
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


def _run_role(
    *,
    cfg: PipelineConfig,
    name: str,
    journal_name: str,
    prompt_fields: dict[str, str],
    reasoning_level: ReasoningLevel,
    task: str,
    input_dirs: tuple[Path, ...],
    private_dir_name: Path,
    tool_names: tuple[str, ...],
    step_hooks: tuple[StepHook, ...],
    extra_readable_dirs: tuple[Path, ...],
    extra_writable_dirs: tuple[Path, ...],
) -> Path:
    """
    Запускает агента роли и ждёт его результата.

        cfg: настройки запуска пайплайна.
        name: имя роли; по нему берётся промпт роли.
        journal_name: имя журнала агента без расширения.
        prompt_fields: значения полей промпта роли.
        reasoning_level: уровень размышления модели агента.
        task: задача агенту.
        input_dirs: папки результатов других агентов.
        private_dir_name: путь личной папки агента внутри папки личных папок.
        tool_names: имена инструментов агента.
        step_hooks: хуки после шага инструментов: замечания к изменённым файлам черновика.
        extra_readable_dirs: папки чтения агента в фазе работы, кроме личной папки и папок результатов
            других агентов.
        extra_writable_dirs: папки записи агента в фазе работы, кроме черновика и файла контекста.

    Возвращает: Папку черновика агента.
    """
    role = RoleSettings(
        name = name,
        system_prompt_path = ROLES_DIR / f"{name}.md",
        prompt_fields = prompt_fields,
        model_name = None,
        reasoning_level = reasoning_level,
        tool_names = tool_names,
        step_hooks = step_hooks,
    )

    return run_role(
        cfg = cfg,
        role = role,
        journal_name = journal_name,
        task = task,
        input_dirs = input_dirs,
        private_dir_name = private_dir_name,
        extra_readable_dirs = extra_readable_dirs,
        extra_writable_dirs = extra_writable_dirs,
    )
