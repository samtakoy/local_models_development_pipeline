from typing import List

from langchain_core.messages import AIMessage, SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict, Annotated

from codeteam.core.pipeline.agent.config import AgentConfig


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

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
    workflow: StateGraph = StateGraph(AgentState) # noqa

    workflow.add_node("agent", agent_node) # noqa
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)

    return workflow.compile()