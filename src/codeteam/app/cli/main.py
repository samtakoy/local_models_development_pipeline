import logging
from datetime import datetime

from codeteam.app.config import load_project_config
from codeteam.app.settings import load_settings
from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.run_agent import run_agent
from codeteam.core.roles import load_role_prompt

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(message)s", datefmt = "%H:%M:%S")
    # httpx пишет строку на каждый запрос к ollama
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    project = load_project_config(
        setup_dir = "/Users/samtakot/devs/learnings/llm-eng/homework/final_project4/codeteam_v2/projects/tree_view"
    )
    run_dir = settings.runs_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"проект: {project.path}")
    logger.info(f"задача: {project.task}")
    logger.info(f"прогон: {run_dir}")

    role = AgentRole(
        name = "architect",
        system_prompt = load_role_prompt(name = "architect"),
        model_name = "qwen3.5:9b",
    )
    result_dir = run_agent(
        role = role,
        task = project.task,
        project_path = project.path,
        journal_path = run_dir / f"01_{role.name}.md",
        settings = settings,
    )
    logger.info(f"черновик: {result_dir}")


if __name__ == "__main__":
    main()
