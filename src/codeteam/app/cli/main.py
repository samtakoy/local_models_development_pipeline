from codeteam.app.config import load_project_config
from codeteam.app.settings import load_settings
from codeteam.core.agent.run_agent import run_agent


def main():
    print("main")
    settings = load_settings()
    project = load_project_config(
        setup_dir = "/Users/samtakot/devs/learnings/llm-eng/homework/final_project4/codeteam_v2/projects/tree_view"
    )
    print(project.path)
    print(project.task)
    run_agent(
        system_prompt = f"Ты архитектор.",
        model_name = "qwen3.5:9b",
        task = project.task,
        project_path = project.path,
        settings = settings
    )


if __name__ == "__main__":
    main()
