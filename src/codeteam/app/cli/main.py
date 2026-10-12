import argparse
import logging
import sys
from pathlib import Path

from codeteam.app.config import load_project_config
from codeteam.app.prompts_db import PROMPTS_ROOT, save_prompts
from codeteam.app.run_dir import make_run_dir_name
from codeteam.app.run_statistics import write_run_report
from codeteam.app.sandbox_check import confirm_unprotected_run
from codeteam.app.settings import load_settings
from codeteam.core.pipeline.run_pipeline import run_pipeline
from codeteam.core.pipeline.state_file import load_state
from codeteam.core.roles.common import PipelineError, read_verdict

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    # httpx пишет строку на каждый запрос к ollama
    logging.getLogger("httpx").setLevel(logging.WARNING)

    arguments = _parse_arguments()
    confirm_unprotected_run()
    settings = load_settings()
    project = load_project_config(setup_dir = arguments.setup_dir)
    run_dir = settings.runs_dir / make_run_dir_name(model_name = settings.agent_model)
    logger.info(f"проект: {project.path}")
    logger.info(f"задача: {project.task}")
    logger.info(f"прогон: {run_dir}")
    resume_state = None if arguments.resume is None else load_state(path = Path(arguments.resume))
    if resume_state is not None:
        logger.info(f"продолжение с роли {resume_state['next_role']}: состояние {arguments.resume}")
    prompts_list = save_prompts(prompts_root = PROMPTS_ROOT, db_dir = settings.prompts_db_dir, run_dir = run_dir)
    logger.info(f"промпты прогона: {prompts_list}")

    try:
        result = run_pipeline(
            project = project,
            run_dir = run_dir,
            model_name = settings.agent_model,
            settings = settings,
            resume_state = resume_state,
        )
    except PipelineError as error:
        logger.error(f"прогон остановлен: {error}")
        sys.exit(1)
    finally:
        # отчёт статистики пишется и после остановки прогона: по уже отработавшим агентам
        logger.info(f"статистика прогона: {write_run_report(run_dir = run_dir)}")

    logger.info(f"отчёт исследователя: {result['research_dir']}")
    logger.info(f"этапы архитектора: {result['plan_dir']}")
    for role_name, report_dir in (("тестировщик", result["tester_dir"]), ("веб-тестировщик", result["web_tester_dir"])):
        if report_dir is not None:
            verdict = "принято" if read_verdict(remarks_dir = report_dir) else "не принято"
            logger.info(f"{role_name}: приложение {verdict}, вердикт и отчёт: {report_dir}")


def _parse_arguments() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Возвращает: Аргументы: setup_dir - папка задачи с файлом set.toml; resume - файл состояния прерванного
        прогона или None.
    """
    parser = argparse.ArgumentParser(description = "Запуск команды агентов на задаче проекта.")
    parser.add_argument("setup_dir", help = "папка задачи с файлом set.toml, например projects/cardviewer_ai")
    parser.add_argument(
        "--resume",
        help = "снимок <журнал роли>.state.json из папки прогона: продолжить с роли, которая шла после этой",
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
