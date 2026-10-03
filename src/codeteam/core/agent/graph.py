from typing import List

from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict, Annotated

from codeteam.core.agent.config import AgentConfig


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

def agent_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    cfg: AgentConfig = config["configurable"]["architector"]
    messages = (
        [
            SystemMessage(content = cfg.system_prompt),
            HumanMessage(content = cfg.task)
        ]
        + state["messages"]
    )

    response = cfg.chat_model.invoke(messages)
    return {"messages": [response]}

def create_agent_graph(
    *, tools: list[BaseTool]
) -> CompiledStateGraph:
    workflow: StateGraph = StateGraph(AgentState) # noqa

    workflow.add_node("agent", agent_node) # noqa
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_edge(START, "agent")

    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    workflow.add_edge("agent", END)

    return workflow.compile()