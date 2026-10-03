from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.common.llm import build_chat_model, OllamaConfig, GenerationMode, ReasoningLevel
from codeteam.core.agent.config import AgentConfig
from codeteam.core.agent.graph import create_agent_graph, AgentState
from codeteam.core.agent.workspace import Workspace, PRIVATE_ROOT
from codeteam.core.tools.files import build_read_tools


def run_agent(
    system_prompt: str,
    model_name: str,
    task: str,
    project_path: str,
    settings: Settings
):

    chat_model: BaseChatModel = build_chat_model(
        config = OllamaConfig(
            base_url = settings.ollama_base_url,
            model = model_name,
            context_window = settings.agent_ctx_window
        ),
        generation_mode = GenerationMode.THINKING,
        reasoning_level = ReasoningLevel.LOW,
    )

    project_dir = Path(project_path).resolve()
    workspace = Workspace(
        project_dir = project_dir,
        private_dir = project_dir / PRIVATE_ROOT / "architect", # TODO зависит от конкретного агента
        readable_dirs = (project_dir,),
        writable_dirs = (),
    )
    tools = build_read_tools(workspace = workspace)

    agent = create_agent_graph(tools = tools)

    config = RunnableConfig(
        configurable = {
            "architector": AgentConfig(
                system_prompt = system_prompt,
                task = task,
                chat_model = chat_model.bind_tools(tools)
            )
        }
    )

    initial_state = AgentState(messages = [])
    events = agent.stream(input = initial_state, config = config)

    for event in events:
        print(event)

