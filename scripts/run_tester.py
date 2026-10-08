"""
Запуск одного тестировщика на готовом проекте, без остальных ролей пайплайна.

Задача берётся из set.toml, чеклист требований — из черновика менеджера продукта в .ct-work проекта
от прошлого прогона. Проект должен быть закоммичен: охрана проекта тестировщика сравнивает с коммитом.

Запуск из папки codeteam_v2:
    uv run python scripts/run_tester.py projects/cardviewer --model qwen3.5:9b
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from codeteam.app.config import load_project_config
from codeteam.app.settings import load_settings
from codeteam.common.git import list_uncommitted_changes
from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PIPELINE_CFG_NAME, PipelineConfig, PipelineState
from codeteam.core.roles.pm import PM_ROLE, REQUIREMENTS_FILE_NAME
from codeteam.core.roles.tester import tester_node

logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Возвращает: Аргументы: setup_dir — папка задачи с файлом set.toml, model — модель тестировщика.
    """
    parser = argparse.ArgumentParser(description = "Запуск одного тестировщика на готовом проекте.")
    parser.add_argument("setup_dir", help = "папка задачи с файлом set.toml, например projects/cardviewer")
    parser.add_argument("--model", required = True, help = "имя модели в ollama, например qwen3.5:9b")

    return parser.parse_args()


def main() -> None:
    """
    Проверяет проект и чеклист, запускает тестировщика и пишет в лог, где лежат его журнал и отчёт.
    """
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    arguments = parse_arguments()
    settings = load_settings()
    project = load_project_config(setup_dir = arguments.setup_dir)
    project_dir = Path(project.path).resolve()

    requirements_dir = draft_dir(private_dir = project_dir / PRIVATE_ROOT / PM_ROLE.name)
    if not (requirements_dir / REQUIREMENTS_FILE_NAME).is_file():
        raise SystemExit(f"нет чеклиста требований {requirements_dir / REQUIREMENTS_FILE_NAME}: нужен прошлый прогон")

    changes = list_uncommitted_changes(project_dir = project_dir)
    if changes:
        raise SystemExit(
            f"в проекте {project_dir} есть незакоммиченные правки: {', '.join(path for _, path in changes)}"
        )

    run_dir = settings.runs_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_tester"
    run_dir.mkdir(parents = True, exist_ok = True)
    logger.info(f"проект: {project_dir}")
    logger.info(f"прогон: {run_dir}")

    config = RunnableConfig(
        configurable = {
            PIPELINE_CFG_NAME: PipelineConfig(
                project_path = project.path,
                run_dir = run_dir,
                model_name = arguments.model,
                review = project.review,
                settings = settings,
            )
        }
    )
    state = PipelineState(
        task = project.task,
        requirements_dir = requirements_dir,
        research_dir = None,
        plan_dir = None,
        stages = None,
        review = None,
        journal_count = 0,
    )
    tester_node(state, config)


if __name__ == "__main__":
    main()
