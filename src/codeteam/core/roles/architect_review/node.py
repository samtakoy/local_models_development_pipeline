"""Узел ревьюера архитектора в графе пайплайна: вердикт и замечания к решению и этапам."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.core.agent.workspace import PRIVATE_ROOT
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Review
from codeteam.core.roles.architect import ARCHITECT_ROLE
from codeteam.core.roles.architect_review.config import ARCHITECT_REVIEW_ROLE
from codeteam.core.roles.architect_review.prompts import ARCHITECT_REVIEW_TASK
from codeteam.core.roles.common import copy_reviewed_draft, make_journal_name, make_rework, next_review_round, \
    read_verdict, role_private_dir_name, run_role
from codeteam.core.roles.pm import REQUIREMENTS_FILE_NAME


def architect_review_node(state: PipelineState, config: RunnableConfig):
    """
    Запускает ревьюера архитектора: он проверяет копию решения и этапов и пишет вердикт с замечаниями.
    Копия черновика архитектора остаётся в его личной папке для сравнения с исправленной версией.
    Если работа не принята и круги не кончились — возвращает её архитектору с прошлым черновиком и контекстом.
    """
    cfg: PipelineConfig = config["configurable"][PIPELINE_CFG_NAME]
    project_dir = Path(cfg.project_path).resolve()
    requirements_dir = state["requirements_dir"]
    review_round = next_review_round(review = state["review"], target = ARCHITECT_ROLE.name)
    private_dir_name = role_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = ARCHITECT_REVIEW_ROLE.name,
        rework = state["rework"],
    )
    reviewed_dir = copy_reviewed_draft(
        draft_dir = state["plan_dir"],
        reviewer_dir = project_dir / PRIVATE_ROOT / private_dir_name,
    )
    remarks_dir = run_role(
        cfg = cfg,
        role = ARCHITECT_REVIEW_ROLE,
        journal_name = make_journal_name(journal_count = state["journal_count"], private_dir_name = private_dir_name),
        task = ARCHITECT_REVIEW_TASK.format(
            task = state["task"],
            requirements_file = (requirements_dir / REQUIREMENTS_FILE_NAME).relative_to(project_dir),
            plan_dir = reviewed_dir.relative_to(project_dir),
        ),
        input_dirs = (requirements_dir, reviewed_dir),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (project_dir,),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )
    review = Review(
        target = ARCHITECT_ROLE.name,
        round = review_round,
        accepted = read_verdict(remarks_dir = remarks_dir),
    )
    rework = make_rework(review = review, remarks_dir = remarks_dir, preserve_draft = True, preserve_context = True)

    return {"review": review, "rework": rework, "journal_count": state["journal_count"] + 1}
