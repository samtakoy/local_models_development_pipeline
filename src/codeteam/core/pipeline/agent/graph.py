from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.state import CompiledStateGraph

from codeteam.core.pipeline.agent.config import AgentConfig


class AgentState(MessagesState):
    pass

def agent_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    cfg: AgentConfig = config["configurable"]["architector"]
    messages = (
        [SystemMessage(content = cfg.system_prompt)]
        + state["messages"]
    )

    response = cfg.chat_model.invoke(messages)
    return {
        "messages": [AIMessage(content=response.content)]
    }

def create_agent_graph() -> CompiledStateGraph:
    workflow = StateGraph(AgentState) # noqa

    workflow.add_node("agent", agent_node) # noqa
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)

    return workflow.compile()