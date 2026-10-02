from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.common.llm import build_chat_model, OllamaConfig, GenerationMode, ReasoningLevel
from codeteam.core.pipeline.agent.config import AgentConfig
from codeteam.core.pipeline.agent.graph import create_agent_graph, AgentState


def run_agent(
    system_prompt: str,
    model_name: str,
    task: str,
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

    agent = create_agent_graph()

    config = RunnableConfig(
        configurable = {
            "architector": AgentConfig(
                system_prompt = system_prompt,
                chat_model = chat_model
            )
        }
    )

    initial_state = AgentState(
        messages = [HumanMessage(content = task)]
    )
    events = agent.stream(initial_state, config = config)

    for event in events:
        print(event)

