from codeteam.app.settings import load_settings
from codeteam.core.pipeline.agent.run_agent import run_agent


def main():
    print("main")
    settings = load_settings()
    run_agent(
        system_prompt = "Ты архитектор",
        model_name = "qwen3.5:9b",
        settings = settings
    )


if __name__ == "__main__":
    main()
