"""Граф пайплайна: кто из агентов за кем идёт и что кому передаётся."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from codeteam.app.settings import Settings
from codeteam.common.git import commit_all
from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.run_agent import run_agent
from codeteam.core.agent.step_hooks import StepHook, code_block_hook
from codeteam.core.agent.workspace import CHECK_DIR, DRAFT_SECTION_PATTERN, PRIVATE_ROOT
from codeteam.core.pipeline.prompts import ARCHITECT_CODE_BLOCK_REMARK, ARCHITECT_TASK, DEVELOPER_TASK, PM_TASK, \
    RESEARCHER_TASK, SENIOR_CODE_BLOCK_REMARK, SENIOR_TASK
from codeteam.core.roles import load_role_prompt
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, GLOB_TOOL_NAME, GREP_TOOL_NAME, \
    READ_TOOL_NAME, WRITE_TOOL_NAME
from codeteam.core.tools.shell import BASH_TOOL_NAME, STOP_PROCESS_TOOL_NAME

logger = logging.getLogger(__name__)

PIPELINE_CFG_NAME = "pipeline"

PM_NODE_ID = "pm"
RESEARCHER_NODE_ID = "researcher"
ARCHITECT_NODE_ID = "architect"
SENIOR_NODE_ID = "senior"
DEVELOPER_NODE_ID = "developer"
FINISH_STAGE_NODE_ID = "finish_stage"

# Файл чеклиста требований в черновике менеджера продукта.
REQUIREMENTS_FILE_NAME = "100_requirements.md"

# Файл общего решения в черновике архитектора.
ARCHITECTURE_FILE_NAME = "000_architecture.md"

# Файл этапа в черновике архитектора — раздел черновика: номер этапа, тема, .md.
STAGE_FILE_PATTERN = DRAFT_SECTION_PATTERN

# Папка этапа внутри личной папки этапа: копии общего решения и файла этапа, вход сеньора.
STAGE_TASK_DIR_NAME = "task"

# Инструменты ролей, которые работают с кодом проекта.
PROJECT_TOOL_NAMES = (
    READ_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
    BASH_TOOL_NAME,
    STOP_PROCESS_TOOL_NAME,
)

# Инструменты ролей, которые работают только со своим черновиком.
DRAFT_TOOL_NAMES = (
    READ_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
)

# Наибольшее число строк в одном блоке кода с указанным языком в черновике архитектора.
ARCHITECT_CODE_BLOCK_LINE_LIMIT = 15

# Наибольшее число строк в одном блоке кода с указанным языком в плане сеньора.
SENIOR_CODE_BLOCK_LINE_LIMIT = 30


class PipelineError(RuntimeError):
    """Результат агента не годится для продолжения пайплайна."""


class PipelineState(TypedDict):
    """
    Состояние пайплайна.

        task: задача пользователя.
        requirements_dir: папка черновика менеджера продукта: чеклист требований; None, пока он не отработал.
        research_dir: папка черновика исследователя; None, пока он не отработал.
        plan_dir: папка черновика архитектора: общее решение и файлы этапов; None, пока он не отработал.
        stage_files: файлы этапов из черновика архитектора по порядку имён.
        stage_index: номер текущего этапа в stage_files, с нуля.
        stage_plan_dir: папка плана сеньора текущего этапа; None, пока он не отработал.
        journal_count: число журналов агентов, уже начатых в прогоне.
    """

    task: str
    requirements_dir: Path | None
    research_dir: Path | None
    plan_dir: Path | None
    stage_files: list[Path]
    stage_index: int
    stage_plan_dir: Path | None
    journal_count: int


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


def pm_node(state: PipelineState, config: RunnableConfig):
    """Запускает менеджера продукта: по тексту задачи пользователя он пишет чеклист требований без доступа к проекту."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    requirements_dir = _run_role(
        cfg = cfg,
        name = PM_NODE_ID,
        journal_name = _journal_name(journal_count = state["journal_count"], label = PM_NODE_ID),
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
        journal_name = _journal_name(journal_count = state["journal_count"], label = RESEARCHER_NODE_ID),
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


def architect_node(state: PipelineState, config: RunnableConfig):
    """Запускает архитектора: по задаче, чеклисту требований и отчёту исследователя он делит работу на этапы."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    research_dir = state["research_dir"]
    task = ARCHITECT_TASK.format(
        task = state["task"],
        requirements_file = (requirements_dir / REQUIREMENTS_FILE_NAME).relative_to(project_dir),
        research_dir = research_dir.relative_to(project_dir),
    )
    plan_dir = _run_role(
        cfg = cfg,
        name = ARCHITECT_NODE_ID,
        journal_name = _journal_name(journal_count = state["journal_count"], label = ARCHITECT_NODE_ID),
        prompt_fields = {},
        reasoning_level = ReasoningLevel.LOW,
        task = task,
        input_dirs = (requirements_dir, research_dir),
        private_dir_name = Path(ARCHITECT_NODE_ID),
        tool_names = PROJECT_TOOL_NAMES,
        step_hooks = (
            code_block_hook(max_lines = ARCHITECT_CODE_BLOCK_LINE_LIMIT, remark = ARCHITECT_CODE_BLOCK_REMARK),
        ),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
    )

    return {
        "plan_dir": plan_dir,
        "stage_files": find_stage_files(plan_dir = plan_dir),
        "journal_count": state["journal_count"] + 1,
    }


def senior_node(state: PipelineState, config: RunnableConfig):
    """Запускает сеньора текущего этапа: по общему решению и файлу этапа он пишет план реализации."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stage_index = state["stage_index"]
    stage_file = state["stage_files"][stage_index]
    stage_dir_name = _stage_dir_name(stage_file = stage_file)
    stage_task_dir = _prepare_stage_task_dir(
        plan_dir = state["plan_dir"],
        stage_file = stage_file,
        target_dir = project_dir / PRIVATE_ROOT / stage_dir_name / STAGE_TASK_DIR_NAME,
    )
    task = SENIOR_TASK.format(
        task = state["task"],
        stage_task_dir = stage_task_dir.relative_to(project_dir),
        architecture_file = ARCHITECTURE_FILE_NAME,
        stage_file = stage_file.name,
    )
    stage_plan_dir = _run_role(
        cfg = cfg,
        name = SENIOR_NODE_ID,
        journal_name = _journal_name(
            journal_count = state["journal_count"],
            label = f"{stage_dir_name}_{SENIOR_NODE_ID}",
        ),
        prompt_fields = {},
        reasoning_level = ReasoningLevel.LOW,
        task = task,
        input_dirs = (stage_task_dir,),
        private_dir_name = stage_dir_name / SENIOR_NODE_ID,
        tool_names = PROJECT_TOOL_NAMES,
        step_hooks = (code_block_hook(max_lines = SENIOR_CODE_BLOCK_LINE_LIMIT, remark = SENIOR_CODE_BLOCK_REMARK),),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
    )

    return {"stage_plan_dir": stage_plan_dir, "journal_count": state["journal_count"] + 1}


def developer_node(state: PipelineState, config: RunnableConfig):
    """Запускает разработчика текущего этапа: по плану сеньора он пишет код этапа в папке проекта."""
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    stage_index = state["stage_index"]
    stage_dir_name = _stage_dir_name(stage_file = state["stage_files"][stage_index])
    stage_plan_dir = state["stage_plan_dir"]
    _run_role(
        cfg = cfg,
        name = DEVELOPER_NODE_ID,
        journal_name = _journal_name(
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
    message = f"codeteam: этап {_stage_number(stage_file = stage_file)} — {_stage_title(stage_file = stage_file)}"
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
        return SENIOR_NODE_ID

    return END


def find_stage_files(*, plan_dir: Path) -> list[Path]:
    """
    Собирает файлы этапов из черновика архитектора.

        plan_dir: папка черновика архитектора.

    Возвращает: Файлы этапов по порядку имён: все файлы вида <номер>_<тема>.md, кроме общего решения.
    """
    if not (plan_dir / ARCHITECTURE_FILE_NAME).is_file():
        raise PipelineError(f"в черновике архитектора {plan_dir} нет файла {ARCHITECTURE_FILE_NAME}")

    stage_files = sorted(
        path
        for path in plan_dir.iterdir()
        if path.is_file() and path.name != ARCHITECTURE_FILE_NAME and STAGE_FILE_PATTERN.match(path.name)
    )
    if not stage_files:
        raise PipelineError(f"в черновике архитектора {plan_dir} нет файлов этапов")

    return stage_files


def create_pipeline_graph() -> CompiledStateGraph:
    """
    Собирает граф пайплайна: менеджер продукта, исследователь, архитектор, затем по каждому этапу
    сеньор, разработчик и коммит этапа.

    Возвращает: Граф пайплайна.
    """
    workflow: StateGraph = StateGraph(PipelineState) # noqa

    workflow.add_node(PM_NODE_ID, pm_node)
    workflow.add_node(RESEARCHER_NODE_ID, researcher_node)
    workflow.add_node(ARCHITECT_NODE_ID, architect_node)
    workflow.add_node(SENIOR_NODE_ID, senior_node)
    workflow.add_node(DEVELOPER_NODE_ID, developer_node)
    workflow.add_node(FINISH_STAGE_NODE_ID, finish_stage_node)

    workflow.add_edge(START, PM_NODE_ID)
    workflow.add_edge(PM_NODE_ID, RESEARCHER_NODE_ID)
    workflow.add_edge(RESEARCHER_NODE_ID, ARCHITECT_NODE_ID)
    workflow.add_conditional_edges(ARCHITECT_NODE_ID, route_next_stage)
    workflow.add_edge(SENIOR_NODE_ID, DEVELOPER_NODE_ID)
    workflow.add_edge(DEVELOPER_NODE_ID, FINISH_STAGE_NODE_ID)
    workflow.add_conditional_edges(FINISH_STAGE_NODE_ID, route_next_stage)

    return workflow.compile()


def _stage_dir_name(*, stage_file: Path) -> Path:
    """
    Строит имя личной папки этапа по файлу этапа.

        stage_file: файл этапа.

    Возвращает: Путь папки этапа внутри папки личных папок: stage_<номер этапа>.
    """
    return Path(f"stage_{_stage_number(stage_file = stage_file)}")


def _stage_number(*, stage_file: Path) -> str:
    """
    Берёт номер этапа из имени файла этапа.

        stage_file: файл этапа.

    Возвращает: Номер этапа, как он записан в имени файла, например 100.
    """
    return STAGE_FILE_PATTERN.match(stage_file.name).group(1)


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


def _prepare_stage_task_dir(*, plan_dir: Path, stage_file: Path, target_dir: Path) -> Path:
    """
    Копирует общее решение архитектора и файл этапа в папку задачи этапа.

        plan_dir: папка черновика архитектора.
        stage_file: файл этапа.
        target_dir: папка задачи этапа.

    Возвращает: Папку задачи этапа.
    """
    target_dir.mkdir(parents = True, exist_ok = True)
    shutil.copy2(plan_dir / ARCHITECTURE_FILE_NAME, target_dir / ARCHITECTURE_FILE_NAME)
    shutil.copy2(stage_file, target_dir / stage_file.name)

    return target_dir


def _journal_name(*, journal_count: int, label: str) -> str:
    """
    Строит имя журнала следующего агента прогона.

        journal_count: число журналов агентов, уже начатых в прогоне.
        label: метка агента в имени журнала: имя роли или папка этапа с именем роли.

    Возвращает: Имя журнала без расширения, например 04_stage_100_senior.
    """
    return f"{journal_count + 1:02d}_{label}"


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
    role = AgentRole(
        name = name,
        system_prompt = load_role_prompt(name = name, fields = prompt_fields),
        model_name = cfg.model_name,
        reasoning_level = reasoning_level,
        tool_names = tool_names,
        step_hooks = step_hooks,
    )

    return run_agent(
        role = role,
        task = task,
        input_dirs = input_dirs,
        project_path = cfg.project_path,
        private_dir_name = private_dir_name,
        extra_readable_dirs = extra_readable_dirs,
        extra_writable_dirs = extra_writable_dirs,
        journal_path = cfg.run_dir / f"{journal_name}.md",
        settings = cfg.settings,
    )
