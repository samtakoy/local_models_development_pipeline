"""Узел архитектора в графе пайплайна: общее решение и этапы."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Stages
from codeteam.core.roles.architect.config import ARCHITECT_ROLE, ARCHITECTURE_FILE_NAME
from codeteam.core.roles.architect.prompts import ARCHITECT_FIX_TASK, ARCHITECT_TASK
from codeteam.core.roles.common import STAGE_FILE_PATTERN, PipelineError, make_journal_name, rework_for, \
    role_private_dir_name, run_role


def architect_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает архитектора: по задаче, чеклисту требований и отчёту исследователя он делит работу на этапы.
    Если работу вернули на доработку — архитектор исправляет черновик, перенесённый в его новую папку, по замечаниям.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    research_dir = state["research_dir"]
    requirements_file = state["requirements_file"].relative_to(project_dir)
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = ARCHITECT_ROLE.name,
        rework = state["rework"],
    )
    rework = rework_for(rework = state["rework"], role_name = ARCHITECT_ROLE.name)
    if rework is not None:
        task = ARCHITECT_FIX_TASK.format(
            task = state["task"],
            requirements_file = requirements_file,
            research_dir = research_dir.relative_to(project_dir),
            plan_dir = draft_dir(private_dir = PRIVATE_ROOT / private_dir_name),
            remarks_dir = rework.remarks_dir.relative_to(project_dir),
        )
        input_dirs = (requirements_dir, research_dir, rework.remarks_dir)
    else:
        task = ARCHITECT_TASK.format(
            task = state["task"],
            requirements_file = requirements_file,
            research_dir = research_dir.relative_to(project_dir),
        )
        input_dirs = (requirements_dir, research_dir)

    journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name)
    plan_dir = run_role(
        cfg = cfg,
        role = ARCHITECT_ROLE,
        journal_name = journal_name,
        task = task,
        input_dirs = input_dirs,
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )

    return {
        "plan_dir": plan_dir,
        "architecture_file": plan_dir / ARCHITECTURE_FILE_NAME,
        "stages": Stages(files = find_stage_files(plan_dir = plan_dir), started = 0, plan_dir = None, fix_rounds = 0),
        "rework": None,
        "journal_name": journal_name,
        "journal_count": state["journal_count"] + 1,
    }


def find_stage_files(*, plan_dir: Path) -> tuple[Path, ...]:
    """
    Собирает файлы этапов из черновика архитектора.

        plan_dir: папка черновика архитектора.

    Возвращает: Файлы этапов по порядку имён: все файлы вида <номер>_<тема>.md, кроме общего решения.
    """
    if not (plan_dir / ARCHITECTURE_FILE_NAME).is_file():
        raise PipelineError(f"в черновике архитектора {plan_dir} нет файла {ARCHITECTURE_FILE_NAME}")

    stage_files = tuple(sorted(
        path
        for path in plan_dir.iterdir()
        if path.is_file() and path.name != ARCHITECTURE_FILE_NAME and STAGE_FILE_PATTERN.match(path.name)
    ))
    if not stage_files:
        raise PipelineError(f"в черновике архитектора {plan_dir} нет файлов этапов")

    return stage_files
