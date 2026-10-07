import logging
import re
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, AIMessage, ToolMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from ollama import ResponseError
from typing import TypedDict, Annotated

from codeteam.core.agent.config import AgentConfig
from codeteam.core.agent.prompts import DONE_ANSWER, TODO_ANSWER
from codeteam.core.agent.workspace import context_path, draft_dir
from codeteam.core.tools.files import READ_TOOL_NAME

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # сколько уже было сбросов истории (компактизаций)
    reset_count: int

AGENT_CFG_NAME = "agent"

INIT_NODE_ID = "init"
AGENT_NODE_ID = "agent"
TOOL_NODE_ID = "tools"
LIMIT_NOTICE_NODE_ID = "limit_notice"
DRAFT_AGENT_NODE_ID = "draft_agent"
DRAFT_TOOL_NODE_ID = "draft_tools"
REINIT_NODE_ID = "reinit"

def init_node(state: AgentState, config: RunnableConfig):
    """Собирает историю агента на старте."""
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    messages = _build_init_prompts(cfg = cfg, with_reinit_notice = False)
    if cfg.warmup_calls:
        messages.append(_warmup_message(calls = cfg.warmup_calls))

    return {"messages": messages}


def reinit_node(state: AgentState, config: RunnableConfig):
    """Пересобирает историю агента после сброса: старт заново и чтение памяти."""
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    memory_calls = [
        # список разделов черновика и контекст работы
        (READ_TOOL_NAME, {"file_path": str(draft_dir(private_dir = cfg.relative_private_dir))}),
        (READ_TOOL_NAME, {"file_path": str(context_path(private_dir = cfg.relative_private_dir))}),
    ]

    # Разделы черновика целиком, по порядку имён: память дороже по токенам.
    # Для сравнения с чтением только списка разделов.
    relative_draft_dir = draft_dir(private_dir = cfg.relative_private_dir)
    absolute_draft_dir = cfg.project_dir / relative_draft_dir
    if absolute_draft_dir.is_dir():
        memory_calls += [
            (READ_TOOL_NAME, {"file_path": str(relative_draft_dir / section.name)})
            for section in sorted(absolute_draft_dir.glob("*.md"))
        ]

    messages = [
        RemoveMessage(id = REMOVE_ALL_MESSAGES),
        *_build_init_prompts(cfg = cfg, with_reinit_notice = True),
        _warmup_message(calls = [*cfg.warmup_calls, *memory_calls]),
    ]

    # то что модель читала до очистки истории - больше не актуально
    cfg.seen_files.forget_all()

    return {"messages": messages, "reset_count": state["reset_count"] + 1}

UNFINISHED_ANSWER_RETRIES = 1
def agent_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    response = _invoke_model(cfg = cfg, messages = state["messages"])
    for _ in range(UNFINISHED_ANSWER_RETRIES):
        if not _is_unfinished(response = response):
            break
        logger.info("[agent] ответ без инструмента и без DONE, повторяю запрос")
        # замечание: повторный запрос действительно помогает в 99% случаев и агент исправляется
        # как усиление на будущее: если посторный запрос не сработал - попробовать еще один
        # с дополнительным хинтом в user message
        response = _invoke_model(cfg = cfg, messages = state["messages"])

    return {"messages": [response]}


SERVER_ERROR_RETRIES = 2
def _invoke_model(*, cfg: AgentConfig, messages: Sequence[BaseMessage]) -> BaseMessage:
    """
    Запрашивает ответ модели, повторяя запрос при ошибке сервера ollama.

        cfg: настройки агента.
        messages: история агента.

    Возвращает: Ответ модели.
    """
    for attempt in range(SERVER_ERROR_RETRIES):
        try:
            return cfg.chat_model.invoke(messages)
        except ResponseError as error:
            logger.warning(f"[agent] ошибка сервера ({error}), повтор {attempt + 1} из {SERVER_ERROR_RETRIES}")

    return cfg.chat_model.invoke(messages)


def limit_notice_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    """
    Дописывает уведомление о лимите в конец результата последнего инструмента.

        state: состояние агента; последнее сообщение истории - результат инструмента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Обновление состояния с результатом инструмента, дополненным уведомлением.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    # Просто испольщовать User Message - просто и работает. Но в этот момент сбрасываются все thinking блоки модели и kv-кеш считается заново
    # return {"messages": [HumanMessage(content = cfg.limit_notice)]}
    last_tool_message: ToolMessage = state["messages"][-1]
    noticed_tool_message = last_tool_message.model_copy(
        update = {"content": f"{last_tool_message.text}\n\n{cfg.limit_notice}"}
    )

    # сообщение с тем же id заменяет прежнее в истории
    return {"messages": [noticed_tool_message]}

def route_after_tools(state: AgentState, config: RunnableConfig) -> str:
    """
    Выбирает узел после выполнения инструментов: продолжение работы или фаза черновика.

        state: состояние агента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Имя следующего узла.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
    input_tokens = _last_input_tokens(messages = state["messages"])
    if input_tokens >= cfg.history_token_hard_limit:
        return LIMIT_NOTICE_NODE_ID

    if input_tokens >= cfg.history_token_limit and not _works_with_answer(cfg = cfg, messages = state["messages"]):
        return LIMIT_NOTICE_NODE_ID

    return AGENT_NODE_ID

def _works_with_answer(*, cfg: AgentConfig, messages: Sequence[BaseMessage]) -> bool:
    """
    Проверяет, работал ли агент на последнем шаге инструментов со своим ответом.

        cfg: настройки агента.
        messages: история агента; в конце - ответ модели с вызовами и результаты этих вызовов.

    Возвращает: True, если успешных вызовов на шаге нет или в аргументах хотя бы одного успешного
        вызова есть путь к личной папке агента: относительный или абсолютный.
    """
    private_paths = (str(cfg.relative_private_dir), str(cfg.project_dir / cfg.relative_private_dir))

    failed_call_ids = set()
    last_response: AIMessage | None = None
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            if message.status == "error":
                failed_call_ids.add(message.tool_call_id)
            continue
        if isinstance(message, AIMessage):
            last_response = message
        break

    if last_response is None:
        return False

    successful_calls = [call for call in last_response.tool_calls if call["id"] not in failed_call_ids]
    if not successful_calls:
        return True

    return any(
        private_path in str(call["args"])
        for call in successful_calls
        for private_path in private_paths
    )

def route_after_draft(state: AgentState, config: RunnableConfig) -> str:
    """
    Выбирает узел после ответа агента в фазе черновика.

        state: состояние агента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Имя следующего узла: инструменты черновика, пересборка истории или конец работы.
        Когда история дошла до края окна модели, инструменты не выполняются.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
    is_window_full = _last_input_tokens(messages = state["messages"]) >= cfg.context_window_limit
    if tools_condition(state) == TOOL_NODE_ID and not is_window_full:
        return DRAFT_TOOL_NODE_ID

    if state["reset_count"] >= cfg.max_resets:
        return END

    return REINIT_NODE_ID


def create_agent_graph(
    *,
    tools: list[BaseTool],
    draft_tools: list[BaseTool],
) -> CompiledStateGraph:

    """
    TODO от основного агента просто завершает прогон - это не продумано
    :param tools:
    :param draft_tools:
    :return:
    """
    tool_names = sorted(tool.name for tool in tools)
    draft_tool_names = sorted(tool.name for tool in draft_tools)
    if tool_names != draft_tool_names:
        raise ValueError(
            f"составы инструментов фаз различаются: работа {tool_names}, черновик {draft_tool_names}"
        )

    workflow: StateGraph = StateGraph(AgentState) # noqa

    workflow.add_node(INIT_NODE_ID, init_node)
    workflow.add_node(AGENT_NODE_ID, agent_node)
    workflow.add_node(TOOL_NODE_ID, ToolNode(tools))
    workflow.add_node(LIMIT_NOTICE_NODE_ID, limit_notice_node)
    workflow.add_node(DRAFT_AGENT_NODE_ID, agent_node)
    workflow.add_node(DRAFT_TOOL_NODE_ID, ToolNode(draft_tools))
    workflow.add_node(REINIT_NODE_ID, reinit_node)

    workflow.add_edge(START, INIT_NODE_ID)

    workflow.add_conditional_edges(
        INIT_NODE_ID,
        tools_condition,
        {TOOL_NODE_ID: TOOL_NODE_ID, END: AGENT_NODE_ID}
    )

    workflow.add_conditional_edges(AGENT_NODE_ID, tools_condition)
    # после вызова тулов основного агента - проверка на лимит по токенам
    workflow.add_conditional_edges(TOOL_NODE_ID, route_after_tools)

    # переходим в режим draft
    workflow.add_edge(LIMIT_NOTICE_NODE_ID, DRAFT_AGENT_NODE_ID)

    workflow.add_conditional_edges(DRAFT_AGENT_NODE_ID, route_after_draft)
    workflow.add_edge(DRAFT_TOOL_NODE_ID, DRAFT_AGENT_NODE_ID)
    workflow.add_conditional_edges(
        REINIT_NODE_ID,
        tools_condition,
        {TOOL_NODE_ID: TOOL_NODE_ID, END: AGENT_NODE_ID}
    )


    return workflow.compile()

def _build_init_prompts(*, cfg: AgentConfig, with_reinit_notice: bool) -> list[BaseMessage]:
    """Собирает стартовые сообщения: системный промпт, задача и сообщение о сбросе."""
    messages: list[BaseMessage] = [
        SystemMessage(content = cfg.system_prompt),
        HumanMessage(content = cfg.task),
    ]
    if with_reinit_notice:
        messages.append(HumanMessage(content = cfg.reinit_notice))

    return messages

def _warmup_message(*, calls: list[tuple[str, dict]]) -> AIMessage:
    """Собирает сообщение с вызовами разогрева: их выполнит узел tools."""
    return AIMessage(
        content = "",
        tool_calls = [
            {"id": f"warmup_{index}", "name": name, "args": args}
            for index, (name, args) in enumerate(calls, start = 1)
        ],
    )

def _last_input_tokens(*, messages: Sequence[BaseMessage]) -> int:
    """
    Находит число входных токенов последнего ответа модели.

        messages: история агента.

    Возвращает: input_tokens последнего AIMessage с usage_metadata; 0, если модель ещё не отвечала.
    """
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.usage_metadata:
            return message.usage_metadata["input_tokens"]

    return 0

DONE_PATTERN = re.compile(rf"\b{DONE_ANSWER}\b")
TODO_PATTERN = re.compile(rf"\b{TODO_ANSWER}\b")

def _is_unfinished(*, response: AIMessage) -> bool:
    """
    Проверяет, что ответ модели не продолжает и не сдаёт работу.

        response: ответ модели.

    Возвращает: True, если в ответе нет ни вызовов инструментов, ни DONE.
    """
    return (
        not response.tool_calls
        and DONE_PATTERN.search(str(response.content)) is None
        and TODO_PATTERN.search(str(response.content)) is None
    )

# Не используется. Прежний признак работы с ответом за мягким лимитом: узел инструментов снимал состояние
# файлов ответа до и после шага и пропускал агента дальше, если файлы изменились. Оставлено на всякий случай.
def _answer_snapshot(*, cfg: AgentConfig) -> dict[Path, tuple[int, int]]:
    """
    Снимает состояние файлов ответа: черновика и контекста.

        cfg: настройки агента.

    Возвращает: Время изменения и размер каждого файла ответа по пути.
    """
    private_dir = cfg.project_dir / cfg.relative_private_dir
    paths = [*draft_dir(private_dir = private_dir).glob("**/*"), context_path(private_dir = private_dir)]

    return {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in paths if path.is_file()}
