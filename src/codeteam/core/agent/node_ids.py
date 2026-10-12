"""Имена узлов графа агента."""

from enum import StrEnum


class AgentNode(StrEnum):
    """
    Имена узлов графа агента.
    """

    INIT = "init"
    AGENT = "agent"
    TOOLS = "tools"
    LIMIT_NOTICE = "limit_notice"
    ANSWER_NOTICE = "answer_notice"
    DRAFT_AGENT = "draft_agent"
    DRAFT_TOOLS = "draft_tools"
    REINIT = "reinit"
