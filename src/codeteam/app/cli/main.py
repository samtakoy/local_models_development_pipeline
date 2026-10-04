import logging
from datetime import datetime

from codeteam.app.config import load_project_config
from codeteam.app.settings import load_settings
from codeteam.core.pipeline.run_pipeline import run_pipeline

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    # httpx пишет строку на каждый запрос к ollama
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    project = load_project_config(
        setup_dir = "/Users/samtakot/devs/learnings/llm-eng/homework/final_project4/codeteam_v2/projects/cards"
    )
    run_dir = settings.runs_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"проект: {project.path}")
    logger.info(f"задача: {project.task}")
    logger.info(f"прогон: {run_dir}")

    result = run_pipeline(project = project, run_dir = run_dir, model_name = "qwen3.5:9b", settings = settings)
    logger.info(f"отчёт исследователя: {result['research_dir']}")
    logger.info(f"этапы архитектора: {result['plan_dir']}")


if __name__ == "__main__":
    main()
