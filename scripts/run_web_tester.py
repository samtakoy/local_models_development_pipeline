"""
Запуск одного веб-тестировщика на готовом проекте, без остальных ролей пайплайна.

Задача берётся из set.toml, чеклист требований — из черновика менеджера продукта в .ct-work проекта
от прошлого прогона. Проект должен быть закоммичен: охрана проекта веб-тестировщика сравнивает с коммитом.

Запуск из папки codeteam_v2:
    uv run python scripts/run_web_tester.py projects/cardviewer --model qwen3.5:9b
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.app.config import load_project_config
from codeteam.app.sandbox_check import confirm_unprotected_run
from codeteam.app.settings import load_settings
from codeteam.common.git import list_uncommitted_changes
from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.run_pipeline import BROWSER_WARM_UP_DIR_NAME
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState, Stages
from codeteam.core.roles.common import PipelineError, last_private_dir_name
from codeteam.core.roles.common.browser import warm_up_browser
from codeteam.core.roles.pm import PM_ROLE, REQUIREMENTS_FILE_NAME
from codeteam.core.roles.web_tester import web_tester_node

logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Возвращает: Аргументы: setup_dir — папка задачи с файлом set.toml, model — модель веб-тестировщика.
    """
    parser = argparse.ArgumentParser(description = "Запуск одного веб-тестировщика на готовом проекте.")
    parser.add_argument("setup_dir", help = "папка задачи с файлом set.toml, например projects/cardviewer")
    parser.add_argument("--model", required = True, help = "имя модели в ollama, например qwen3.5:9b")

    return parser.parse_args()


def main() -> None:
    """
    Проверяет проект и чеклист, запускает веб-тестировщика и пишет в лог, где лежат его журнал и отчёт.
    """
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    arguments = parse_arguments()
    confirm_unprotected_run()
    settings = load_settings()
    project = load_project_config(setup_dir = arguments.setup_dir)
    if not project.browser_check:
        raise SystemExit(f"в {arguments.setup_dir}/set.toml проверка в браузере выключена: browser_check = false")
    project_dir = Path(project.path).resolve()

    pm_dir_name = last_private_dir_name(project_dir = project_dir, parent = Path("."), role_name = PM_ROLE.name)
    if pm_dir_name is None:
        raise SystemExit(f"нет папки менеджера продукта в {project_dir / PRIVATE_ROOT}: нужен прошлый прогон")

    requirements_dir = draft_dir(private_dir = project_dir / PRIVATE_ROOT / pm_dir_name)
    requirements_file = requirements_dir / REQUIREMENTS_FILE_NAME
    if not requirements_file.is_file():
        raise SystemExit(f"нет чеклиста требований {requirements_file}: нужен прошлый прогон")

    changes = list_uncommitted_changes(project_dir = project_dir)
    if changes:
        raise SystemExit(
            f"в проекте {project_dir} есть незакоммиченные правки: {', '.join(path for _, path in changes)}"
        )

    run_dir = settings.runs_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_web_tester"
    run_dir.mkdir(parents = True, exist_ok = True)
    logger.info(f"проект: {project_dir}")
    logger.info(f"прогон: {run_dir}")
    try:
        warm_up_browser(work_dir = run_dir / BROWSER_WARM_UP_DIR_NAME)
    except PipelineError as error:
        raise SystemExit(str(error)) from error

    config = RunnableConfig(
        configurable = {
            PIPELINE_CFG_NAME: PipelineConfig(
                project_path = project.path,
                run_dir = run_dir,
                model_name = arguments.model,
                roles = project.roles,
                browser_check = project.browser_check,
                settings = settings,
            )
        }
    )
    state = PipelineState(
        task = project.task,
        requirements_dir = requirements_dir,
        requirements_file = requirements_file,
        research_dir = None,
        plan_dir = None,
        architecture_file = None,
        # этапов нет: веб-тестировщик проверяет готовый проект, этап исправлений скрипт не запускает
        stages = Stages(files = (), started = 0, plan_dir = None, fix_rounds = 0),
        review = None,
        rework = None,
        web_test_dir = None,
        next_role = None,
        journal_name = None,
        journal_count = 0,
    )
    web_tester_node(state, config)


if __name__ == "__main__":
    main()
