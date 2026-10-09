"""Узел архитектора в графе пайплайна: общее решение и этапы."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Stages
from codeteam.core.roles.architect.config import ARCHITECT_ROLE, ARCHITECTURE_FILE_NAME
from codeteam.core.roles.architect.prompts import ARCHITECT_FIX_TASK, ARCHITECT_TASK
from codeteam.core.roles.common import STAGE_FILE_PATTERN, PipelineError, make_journal_name, needs_fix, run_role
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME


def architect_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает архитектора: по задаче, чеклисту требований и отчёту исследователя он делит работу на этапы.
    Если ревьюер вернул работу на доработку — архитектор исправляет свой черновик по замечаниям.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    research_dir = state["research_dir"]
    requirements_file = (requirements_dir / REQUIREMENTS_FILE_NAME).relative_to(project_dir)
    review = state["review"]
    if needs_fix(review = review, target = ARCHITECT_ROLE.name):
        task = ARCHITECT_FIX_TASK.format(
            task = state["task"],
            requirements_file = requirements_file,
            research_dir = research_dir.relative_to(project_dir),
            plan_dir = state["plan_dir"].relative_to(project_dir),
            remarks_dir = review.remarks_dir.relative_to(project_dir),
        )
        input_dirs = (requirements_dir, research_dir, review.remarks_dir)
        label = f"{ARCHITECT_ROLE.name}_fix_{review.round}"
    else:
        task = ARCHITECT_TASK.format(
            task = state["task"],
            requirements_file = requirements_file,
            research_dir = research_dir.relative_to(project_dir),
        )
        input_dirs = (requirements_dir, research_dir)
        label = ARCHITECT_ROLE.name

    plan_dir = run_role(
        cfg = cfg,
        role = ARCHITECT_ROLE,
        journal_name = make_journal_name(journal_count = state["journal_count"], label = label),
        task = task,
        input_dirs = input_dirs,
        private_dir_name = Path(ARCHITECT_ROLE.name),
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
    )

    return {
        "plan_dir": plan_dir,
        "stages": Stages(files = find_stage_files(plan_dir = plan_dir), index = 0, plan_dir = None, fix_rounds = 0),
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
