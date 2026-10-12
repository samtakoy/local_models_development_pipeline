"""
Запуск одного помощника с браузером на уже запущенном приложении, без остальных ролей пайплайна.

Приложение запускает пользователь сам. Помощник проходит сценарии по адресу и пишет наблюдения в черновик.
Журнал помощника — в папке прогона <время>_<модель>_bro_check, время обработки каждой картинки
describe_picture — в логе.

Запуск из папки codeteam_v2:
    uv run python scripts/run_browser_checker.py projects/cardviewer \\
        --model qwen3.6:35b-a3b-coding-nvfp4 \\
        --url http://127.0.0.1:8050 \\
        --scenarios "Открой главную страницу. Открой любую колоду. Переверни первую карточку."
"""

import argparse
import logging
from pathlib import Path

from codeteam.app.config import load_project_config
from codeteam.app.run_dir import make_run_dir_name
from codeteam.app.settings import load_settings
from codeteam.core.pipeline.run_pipeline import BROWSER_WARM_UP_DIR_NAME
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.browser_checker import BROWSER_CHECKER_ROLE, OBSERVATIONS_FILE_NAME
from codeteam.core.roles.browser_checker.prompts import BROWSER_CHECK_TASK
from codeteam.core.roles.common import PipelineError, make_journal_name, reserve_private_dir_name, run_role
from codeteam.core.roles.common.browser import warm_up_browser

logger = logging.getLogger(__name__)

# Роль, от имени которой помощник получает просьбу.
CALLER_NAME = "tester"


def parse_arguments() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Возвращает: Аргументы: setup_dir — папка задачи с файлом set.toml, model — модель помощника, url — адрес
        запущенного приложения, scenarios — сценарии проверки.
    """
    parser = argparse.ArgumentParser(description = "Запуск одного помощника с браузером на запущенном приложении.")
    parser.add_argument("setup_dir", help = "папка задачи с файлом set.toml, например projects/cardviewer")
    parser.add_argument("--model", required = True, help = "имя модели в ollama")
    parser.add_argument("--url", required = True, help = "адрес запущенного приложения, например http://127.0.0.1:8050")
    parser.add_argument("--scenarios", required = True, help = "сценарии проверки по шагам")

    return parser.parse_args()


def main() -> None:
    """
    Запускает помощника с браузером и пишет в лог, где лежат его журнал и наблюдения.
    """
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    arguments = parse_arguments()
    settings = load_settings()
    project = load_project_config(setup_dir = arguments.setup_dir)
    project_dir = Path(project.path).resolve()

    run_dir = settings.runs_dir / f"{make_run_dir_name(model_name = arguments.model)}_bro_check"
    run_dir.mkdir(parents = True, exist_ok = True)
    logger.info(f"проект: {project_dir}")
    logger.info(f"прогон: {run_dir}")
    try:
        warm_up_browser(work_dir = run_dir / BROWSER_WARM_UP_DIR_NAME)
    except PipelineError as error:
        raise SystemExit(str(error)) from error

    cfg = PipelineConfig(
        project_path = project.path,
        run_dir = run_dir,
        model_name = arguments.model,
        roles = project.roles,
        browser_check = True,
        settings = settings,
    )
    private_dir_name = reserve_private_dir_name(
        project_dir = project_dir,
        parent = Path("."),
        role_name = BROWSER_CHECKER_ROLE.name,
        preserve_draft = False,
        preserve_context = False,
    )
    journal_name = make_journal_name(journal_count = 0, private_dir_name = private_dir_name)
    observations_dir = run_role(
        cfg = cfg,
        role = BROWSER_CHECKER_ROLE,
        journal_name = journal_name,
        task = BROWSER_CHECK_TASK.format(caller_name = CALLER_NAME, url = arguments.url, scenarios = arguments.scenarios),
        input_dirs = (),
        private_dir_name = private_dir_name,
        extra_readable_dirs = (),
        extra_writable_dirs = (),
        extra_command_writable_dirs = (),
    )
    logger.info(f"журнал: {run_dir / journal_name}.md")
    logger.info(f"наблюдения: {observations_dir / OBSERVATIONS_FILE_NAME}")


if __name__ == "__main__":
    main()
