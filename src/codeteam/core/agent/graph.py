from collections.abc import Sequence

from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict, Annotated

from codeteam.core.agent.config import AgentConfig


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

AGENT_CFG_NAME = "agent"

def init_node(
    state: AgentState,
    config: RunnableConfig
):
    """Инициализация истории агента на старте"""
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
    calls = [
        {"id": f"warmup_{index}", "name": name, "args": args}
        for index, (name, args) in enumerate(cfg.warmup_calls, start = 1)
    ]
    messages: list[BaseMessage] = [
        SystemMessage(content = cfg.system_prompt),
        HumanMessage(content = cfg.task)
    ]
    if calls:
        messages.append(AIMessage(content = "", tool_calls = calls))

    return {"messages": messages}


def agent_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    response = cfg.chat_model.invoke(state["messages"])
    return {"messages": [response]}

def create_agent_graph(
    *, tools: list[BaseTool]
) -> CompiledStateGraph:
    TOOL_NODE_ID = "tools"
    AGENT_NODE_ID = "agent"
    INIT_NODE_ID = "init"

    workflow: StateGraph = StateGraph(AgentState) # noqa

    workflow.add_node(INIT_NODE_ID, init_node)
    workflow.add_node(AGENT_NODE_ID, agent_node)
    workflow.add_node(TOOL_NODE_ID, ToolNode(tools))

    workflow.add_edge(START, INIT_NODE_ID)

    workflow.add_conditional_edges(
        INIT_NODE_ID,
        tools_condition,
        {TOOL_NODE_ID: TOOL_NODE_ID, END: AGENT_NODE_ID}
    )

    workflow.add_conditional_edges(AGENT_NODE_ID, tools_condition)
    workflow.add_edge(TOOL_NODE_ID, AGENT_NODE_ID)

    return workflow.compile()