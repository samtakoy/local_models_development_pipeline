"""Запуск пайплайна агентов на задаче проекта."""

from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.core.pipeline.graph import create_pipeline_graph
from codeteam.core.pipeline.project import ProjectSettings
from codeteam.core.pipeline.project_setup import prepare_project
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.advisor.documentation import warm_up_documentation
from codeteam.core.roles.common import PipelineError
from codeteam.core.roles.common.browser import warm_up_browser
from codeteam.core.roles.developer import DEVELOPER_ROLE
from codeteam.core.roles.senior import SENIOR_ROLE

# Папка прогрева браузера в папке прогона.
BROWSER_WARM_UP_DIR_NAME = "browser_warm_up"

# Папка прогрева сервера документации в папке прогона.
DOCUMENTATION_WARM_UP_DIR_NAME = "documentation_warm_up"

# Роли, у которых в помощниках советник по документации.
LIBRARY_DOCS_ROLE_NAMES = (SENIOR_ROLE.name, DEVELOPER_ROLE.name)


def run_pipeline(
    *,
    project: ProjectSettings,
    run_dir: Path,
    model_name: str,
    settings: Settings,
    resume_state: PipelineState | None,
) -> PipelineState:
    """
    Проверяет браузер, если проверка в браузере включена, и сервер документации советника, если советник
    включён и в ролях есть роль, которая его зовёт, готовит папку проекта, запускает пайплайн агентов на задаче проекта и ждёт окончания.

        project: проект и задача пользователя.
        run_dir: папка прогона: журналы агентов и файл состояния.
        model_name: модель агентов.
        settings: настройки приложения.
        resume_state: состояние прерванного прогона: пайплайн продолжается с его next_role, личные папки
            остаются на месте; None - новый прогон с первой роли.

    Возвращает: Итоговое состояние пайплайна: папки результатов агентов.
    """
    graph = create_pipeline_graph(roles = project.roles)
    if resume_state is not None:
        _check_resume_state(resume_state = resume_state, roles = project.roles)

    if project.browser_check:
        warm_up_browser(work_dir = run_dir / BROWSER_WARM_UP_DIR_NAME, npm_cache_dir = settings.npm_cache_dir)

    if project.library_docs and any(role_name in project.roles for role_name in LIBRARY_DOCS_ROLE_NAMES):
        warm_up_documentation(
            work_dir = run_dir / DOCUMENTATION_WARM_UP_DIR_NAME,
            npm_cache_dir = settings.npm_cache_dir,
            api_key = settings.context7_api_key,
            check_key = settings.context7_check_key_at_start,
        )

    prepare_project(
        project_dir = Path(project.path).resolve(),
        run_name = run_dir.name,
        archive_private_dirs = resume_state is None,
    )

    config = RunnableConfig(
        configurable = {
            PIPELINE_CFG_NAME: PipelineConfig(
                project_path = project.path,
                run_dir = run_dir,
                model_name = model_name,
                roles = project.roles,
                browser_check = project.browser_check,
                library_docs = project.library_docs,
                settings = settings,
            )
        }
    )
    if resume_state is not None:
        return graph.invoke(input = resume_state, config = config)

    initial_state = PipelineState(
        task = project.task,
        requirements_dir = None,
        requirements_file = None,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        stages = None,
        review = None,
        rework = None,
        tester_dir = None,
        web_scenarios_dir = None,
        web_tester_dir = None,
        acceptance_dir = None,
        next_role = project.roles[0],
        journal_name = None,
        journal_count = 0,
    )

    return graph.invoke(input = initial_state, config = config)


def _check_resume_state(*, resume_state: PipelineState, roles: tuple[str, ...]) -> None:
    """
    Проверяет, что с состояния можно продолжить прогон: прогон не закончен и его следующая роль есть в списке ролей.
    Ошибку поднимает PipelineError.

        resume_state: состояние прерванного прогона.
        roles: последовательность ролей пайплайна.
    """
    next_role = resume_state["next_role"]
    if next_role is None:
        raise PipelineError("продолжить нельзя: прогон из файла состояния уже закончен")

    if next_role not in roles:
        raise PipelineError(f"продолжить нельзя: роли {next_role} нет в списке ролей {', '.join(roles)}")
