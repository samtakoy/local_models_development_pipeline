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

def init_node(
    state: AgentState,
    config: RunnableConfig
):
    """Инициализация истории агента на старте"""
    cfg: AgentConfig = config["configurable"]["architector"]

    """
    call = AIMessage(
        content = "",
        tool_calls = [{"id": "warmup_1", "name": read_file.name, "args": {"path": "."}}],
    )
    result = ToolMessage(content = read_file.invoke({"path": "."}), tool_call_id = "warmup_1")
    """

    return {
        "messages": [
            SystemMessage(content = cfg.system_prompt),
            HumanMessage(content = cfg.task),
            # call,
            # result
        ]
    }

def agent_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    cfg: AgentConfig = config["configurable"]["architector"]

    response = cfg.chat_model.invoke(state["messages"])
    return {"messages": [response]}

def create_agent_graph(
    *, tools: list[BaseTool]
) -> CompiledStateGraph:
    workflow: StateGraph = StateGraph(AgentState) # noqa

    workflow.add_node("init", init_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "init")
    workflow.add_edge("init", "agent")

    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    # workflow.add_edge("agent", END)

    return workflow.compile()