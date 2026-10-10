import logging
import re
from collections.abc import Callable, Sequence
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
from codeteam.core.agent.node_ids import AGENT_NODE_ID, ANSWER_NOTICE_NODE_ID, DRAFT_AGENT_NODE_ID, \
    DRAFT_TOOL_NODE_ID, INIT_NODE_ID, LIMIT_NOTICE_NODE_ID, REINIT_NODE_ID, TOOL_NODE_ID
from codeteam.core.agent.statistics import ANSWER_COMMAND_REMARK_COUNTER, SERVER_ERROR_RETRY_COUNTER, \
    STEP_CHECK_REMARK_COUNTER, STEP_HOOK_REMARK_COUNTER, UNFINISHED_ANSWER_RETRY_COUNTER
from codeteam.core.agent.prompts import ANSWER_CHECK_NOTICE, ANSWER_COMMAND_REMARK, DONE_ANSWER, TODO_ANSWER, \
    UNFINISHED_ANSWER_NOTICE
from codeteam.core.agent.workspace import context_path, draft_dir
from codeteam.core.tools.files import READ_TOOL_NAME
from codeteam.core.tools.shell import BASH_TOOL_NAME

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # сколько уже было сбросов истории (компактизаций)
    reset_count: int
    # сколько раз агент сдавал работу, не прошедшую проверку сдачи, и получал отказ
    answer_notices: int

AGENT_CFG_NAME = "agent"

# Сколько раз отказывать агенту, чья работа не прошла проверку сдачи; дальше работа переходит к новому агенту.
ANSWER_NOTICE_LIMIT = 3

def init_node(state: AgentState, config: RunnableConfig):
    """Собирает историю агента на старте."""
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    messages = _build_init_prompts(cfg = cfg, with_reinit_notice = False)
    if cfg.warmup_calls:
        messages.append(_warmup_message(calls = cfg.warmup_calls))

    return {"messages": messages}


def reinit_node(state: AgentState, config: RunnableConfig):
    """
    Пересобирает историю агента после сброса: старт заново и чтение памяти; снимает фоновые процессы
    прежнего агента и обнуляет счётчик отказов в приёме работы.
    """
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

    # фоновые процессы прежнего агента снимаются
    cfg.shell_processes.kill_all()

    # новый агент получает свои попытки сдачи
    return {"messages": messages, "reset_count": state["reset_count"] + 1, "answer_notices": 0}

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
        cfg.statistics.count(name = UNFINISHED_ANSWER_RETRY_COUNTER)
        # замечание: повторный запрос действительно помогает в 99% случаев и агент исправляется
        # как усиление на будущее: если посторный запрос не сработал - попробовать еще один
        # с дополнительным хинтом в user message
        response = _invoke_model(cfg = cfg, messages = state["messages"])

    if _is_unfinished(response = response):
        logger.info("[agent] ответ снова без инструмента и без DONE, повторяю запрос с подсказкой")
        hint = HumanMessage(content = UNFINISHED_ANSWER_NOTICE)
        response = _invoke_model(cfg = cfg, messages = [*state["messages"], hint])

        return {"messages": [hint, response]}

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
            cfg.statistics.count(name = SERVER_ERROR_RETRY_COUNTER)

    return cfg.chat_model.invoke(messages)


def limit_notice_node(
    state: AgentState,
    config: RunnableConfig
) -> AgentState:
    """
    Снимает фоновые процессы агента и дописывает уведомление о лимите в конец результата
    последнего инструмента.

        state: состояние агента; последнее сообщение истории - результат инструмента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Обновление состояния с результатом инструмента, дополненным уведомлением.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    # в фазе черновика запускать нельзя: фоновые процессы агента снимаются
    cfg.shell_processes.kill_all()

    # Просто испольщовать User Message - просто и работает. Но в этот момент сбрасываются все thinking блоки модели и kv-кеш считается заново
    # return {"messages": [HumanMessage(content = cfg.limit_notice)]}
    last_tool_message: ToolMessage = state["messages"][-1]
    noticed_tool_message = last_tool_message.model_copy(
        update = {"content": f"{last_tool_message.text}\n\n{cfg.limit_notice}"}
    )

    # сообщение с тем же id заменяет прежнее в истории
    return {"messages": [noticed_tool_message]}

def answer_notice_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Отказывает в приёме работы, не прошедшей проверку сдачи: добавляет агенту сообщение с отказом.

        state: состояние агента; последнее сообщение истории - ответ агента с DONE.
        config: конфигурация запуска с настройками агента.

    Возвращает: Обновление состояния с сообщением об отказе и увеличенным счётчиком отказов.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]

    return {
        "messages": [HumanMessage(content = _answer_notice(cfg = cfg))],
        "answer_notices": state["answer_notices"] + 1,
    }

def route_after_agent(state: AgentState, config: RunnableConfig) -> str:
    """
    Выбирает узел после ответа агента: инструменты, отказ в приёме работы, передача работы новому
    агенту или конец работы.

    Работа, не прошедшая проверку сдачи после ANSWER_NOTICE_LIMIT отказов, переходит к новому агенту
    через пересборку истории; после max_resets сбросов работа завершается как есть.

        state: состояние агента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Имя следующего узла.
    """
    if tools_condition(state) == TOOL_NODE_ID:
        return TOOL_NODE_ID

    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
    response = state["messages"][-1]
    is_done = DONE_PATTERN.search(str(response.content)) is not None
    if not is_done or _answer_notice(cfg = cfg) is None:
        return END

    if state["answer_notices"] < ANSWER_NOTICE_LIMIT:
        return ANSWER_NOTICE_NODE_ID

    # попытки сдачи кончились: работу доделывает новый агент
    if state["reset_count"] < cfg.max_resets:
        return REINIT_NODE_ID

    return END

def make_tools_node(*, tools: list[BaseTool]) -> Callable:
    """
    Собирает узел инструментов, который после шага запускает хуки на изменённых файлах черновика
    и проверки после шага, а на попытку сдать работу командой даёт замечание.

        tools: инструменты узла.

    Возвращает: Узел графа.
    """
    tool_node = ToolNode(tools)

    def tools_node(state: AgentState, config: RunnableConfig):
        """
        Выполняет вызовы инструментов и дописывает к результату последнего вызова замечания хуков,
        проверок и замечание о сдаче работы командой.
        """
        cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
        is_answer_command = _is_answer_command(response = state["messages"][-1])
        if not cfg.step_hooks and not cfg.step_checks and not is_answer_command:
            return tool_node.invoke(state, config)

        before = _private_dir_snapshot(cfg = cfg)
        update = tool_node.invoke(state, config)
        hook_remarks = _step_hook_remarks(cfg = cfg, before = before, after = _private_dir_snapshot(cfg = cfg))
        check_remarks = [remark for check in cfg.step_checks if (remark := check()) is not None]
        for _ in hook_remarks:
            cfg.statistics.count(name = STEP_HOOK_REMARK_COUNTER)
        for _ in check_remarks:
            cfg.statistics.count(name = STEP_CHECK_REMARK_COUNTER)
        remarks = [*hook_remarks, *check_remarks]
        if is_answer_command:
            cfg.statistics.count(name = ANSWER_COMMAND_REMARK_COUNTER)
            remarks.append(ANSWER_COMMAND_REMARK)
        if not remarks:
            return update

        tool_messages = list(update["messages"])
        last_tool_message = tool_messages[-1]
        tool_messages[-1] = last_tool_message.model_copy(
            update = {"content": "\n\n".join([last_tool_message.text, *remarks])}
        )

        return {**update, "messages": tool_messages}

    return tools_node

def route_after_tools(state: AgentState, config: RunnableConfig) -> str:
    """
    Выбирает узел после выполнения инструментов: продолжение работы или фаза черновика.

    Мягкий лимит history_token_limit не действует на шаге, где агент работал со своим ответом
    или пытался сдать работу командой; жёсткий лимит history_token_hard_limit действует всегда.

        state: состояние агента.
        config: конфигурация запуска с настройками агента.

    Возвращает: Имя следующего узла.
    """
    cfg: AgentConfig = config["configurable"][AGENT_CFG_NAME]
    input_tokens = _last_input_tokens(messages = state["messages"])
    if input_tokens >= cfg.history_token_hard_limit:
        return LIMIT_NOTICE_NODE_ID

    is_answer_step = (
        _works_with_answer(cfg = cfg, messages = state["messages"])
        or _is_answer_command(response = _last_response(messages = state["messages"]))
    )
    if input_tokens >= cfg.history_token_limit and not is_answer_step:
        return LIMIT_NOTICE_NODE_ID

    return AGENT_NODE_ID


def _is_answer_command(*, response: BaseMessage | None) -> bool:
    """
    Проверяет, что ответ модели — попытка сдать работу командой: все вызовы — bash с командой
    из одного echo или printf со словом DONE или TODO.

        response: ответ модели.

    Возвращает: True, если в ответе есть вызовы инструментов и все они такие команды.
    """
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return False

    return all(
        call["name"] == BASH_TOOL_NAME
        and ANSWER_COMMAND_PATTERN.fullmatch(str(call["args"].get("command", ""))) is not None
        for call in response.tool_calls
    )


def _last_response(*, messages: Sequence[BaseMessage]) -> AIMessage | None:
    """
    Находит последний ответ модели в истории.

        messages: история агента.

    Возвращает: Последний ответ модели или None, если ответов нет.
    """
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message

    return None

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
    workflow.add_node(TOOL_NODE_ID, make_tools_node(tools = tools))
    workflow.add_node(LIMIT_NOTICE_NODE_ID, limit_notice_node)
    workflow.add_node(ANSWER_NOTICE_NODE_ID, answer_notice_node)
    workflow.add_node(DRAFT_AGENT_NODE_ID, agent_node)
    workflow.add_node(DRAFT_TOOL_NODE_ID, make_tools_node(tools = draft_tools))
    workflow.add_node(REINIT_NODE_ID, reinit_node)

    workflow.add_edge(START, INIT_NODE_ID)

    workflow.add_conditional_edges(
        INIT_NODE_ID,
        tools_condition,
        {TOOL_NODE_ID: TOOL_NODE_ID, END: AGENT_NODE_ID}
    )

    workflow.add_conditional_edges(AGENT_NODE_ID, route_after_agent)
    # после отказа в приёме работы агент продолжает работу
    workflow.add_edge(ANSWER_NOTICE_NODE_ID, AGENT_NODE_ID)
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

def _answer_notice(*, cfg: AgentConfig) -> str | None:
    """
    Проверяет черновик агента при сдаче работы: черновик не пуст и проходит проверки сдачи роли.

        cfg: настройки агента.

    Возвращает: Сообщение с отказом агенту или None, если работу можно принять.
    """
    relative_draft_dir = draft_dir(private_dir = cfg.relative_private_dir)
    agent_draft_dir = cfg.project_dir / relative_draft_dir
    if not any(agent_draft_dir.glob("*.md")):
        return cfg.empty_draft_notice

    remarks = [remark for check in cfg.answer_checks if (remark := check(agent_draft_dir)) is not None]
    if not remarks:
        return None

    return ANSWER_CHECK_NOTICE.format(draft_dir = relative_draft_dir, remarks = "\n".join(remarks))


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

# Команда bash, которой агент пытается сдать работу: один echo или printf со словом DONE или TODO.
ANSWER_COMMAND_PATTERN = re.compile(rf"""\s*(echo|printf)\s+["']?({DONE_ANSWER}|{TODO_ANSWER})["']?\s*""")

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

def _step_hook_remarks(
    *,
    cfg: AgentConfig,
    before: dict[Path, tuple[int, int]],
    after: dict[Path, tuple[int, int]],
) -> list[str]:
    """
    Запускает хуки после шага на файлах личной папки, которые появились или изменились за шаг: каждый
    файл получают хуки, в чьей папке он лежит.

        cfg: настройки агента.
        before: состояние файлов личной папки до шага.
        after: состояние файлов личной папки после шага.

    Возвращает: Замечания хуков по порядку файлов и хуков; пустой список, если замечаний нет.
    """
    private_dir = cfg.project_dir / cfg.relative_private_dir
    changed_files = sorted(path for path, state in after.items() if before.get(path) != state)

    remarks = []
    for path in changed_files:
        folder_hooks = [
            folder_hook for folder_hook in cfg.step_hooks if path.is_relative_to(private_dir / folder_hook.folder)
        ]
        if not folder_hooks:
            continue

        text = path.read_text(encoding = "utf-8", errors = "replace")
        for folder_hook in folder_hooks:
            remark = folder_hook.hook(path, text)
            if remark is not None:
                remarks.append(remark)

    return remarks

def _private_dir_snapshot(*, cfg: AgentConfig) -> dict[Path, tuple[int, int]]:
    """
    Снимает состояние файлов личной папки агента со всеми подпапками.

        cfg: настройки агента.

    Возвращает: Время изменения и размер каждого файла по пути.
    """
    private_dir = cfg.project_dir / cfg.relative_private_dir

    return {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in private_dir.glob("**/*") if path.is_file()}
