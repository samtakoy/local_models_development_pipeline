import argparse
import logging
import sys
from datetime import datetime

from codeteam.app.config import load_project_config
from codeteam.app.sandbox_check import confirm_unprotected_run
from codeteam.app.settings import load_settings
from codeteam.core.pipeline.run_pipeline import run_pipeline
from codeteam.core.roles.common import PipelineError

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    # httpx пишет строку на каждый запрос к ollama
    logging.getLogger("httpx").setLevel(logging.WARNING)

    arguments = _parse_arguments()
    confirm_unprotected_run()
    settings = load_settings()
    project = load_project_config(setup_dir = arguments.setup_dir)
    run_dir = settings.runs_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"проект: {project.path}")
    logger.info(f"задача: {project.task}")
    logger.info(f"прогон: {run_dir}")

    try:
        result = run_pipeline(project = project, run_dir = run_dir, model_name = "qwen3.5:9b", settings = settings)
    except PipelineError as error:
        logger.error(f"прогон остановлен: {error}")
        sys.exit(1)

    logger.info(f"отчёт исследователя: {result['research_dir']}")
    logger.info(f"этапы архитектора: {result['plan_dir']}")


def _parse_arguments() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Возвращает: Аргументы: setup_dir - папка задачи с файлом set.toml.
    """
    parser = argparse.ArgumentParser(description = "Запуск команды агентов на задаче проекта.")
    parser.add_argument("setup_dir", help = "папка задачи с файлом set.toml, например projects/cardviewer_ai")

    return parser.parse_args()


if __name__ == "__main__":
    main()
