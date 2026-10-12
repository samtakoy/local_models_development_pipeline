from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from codeteam.app.settings import Settings
from codeteam.common.llm import build_chat_model, OllamaConfig, GenerationMode, ReasoningLevel
from codeteam.core.agent.answer_files import build_draft_rules
from codeteam.core.agent.config import AgentConfig
from codeteam.core.agent.graph import create_agent_graph, AgentState, AGENT_CFG_NAME
from codeteam.core.agent.journal import AgentJournal
from codeteam.core.agent.repeat_check import INITIAL_REPEAT_STATE
from codeteam.core.agent.statistics import STATISTICS_FILE_SUFFIX, AgentStatistics
from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.prompts import DRAFT_PHASE_BASH_REFUSAL, AGENT_SYSTEM_INSTRUCTIONS, LIMIT_NOTICE, \
    DRAFT_PHASE_HELPER_TOOL_REFUSAL, DRAFT_PHASE_START_SERVICE_REFUSAL, REINIT_NOTICE, EMPTY_DRAFT_NOTICE, PROJECT_RULES_FILE_NAME, PROJECT_RULES_INSTRUCTIONS, PROJECT_DOCS_DIR_NAME, \
    TODAY_INSTRUCTIONS, CODE_NAME_INSTRUCTIONS
from codeteam.core.agent.workspace import CONTEXT_FILE_NAME, PRIVATE_ROOT, Workspace, context_path, draft_dir, \
    helpers_dir
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, READ_TOOL_NAME, WRITE_TOOL_NAME, \
    file_tool_builders, PathRefusals, SeenFiles
from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.tools.disabled import build_disabled_tool
from codeteam.core.tools.shell import BASH_TOOL_NAME, START_SERVICE_TOOL_NAME, STOP_PROCESS_TOOL_NAME, \
    build_bash_tool, build_disabled_bash_tool, build_disabled_start_service_tool, build_start_service_tool, \
    build_stop_process_tool


# Запас токенов окна модели на её ответ.
RESPONSE_TOKEN_RESERVE = 16000

# Предел шагов графа агента, одинаковый для любого места запуска: без явного значения агент, запущенный
# из инструмента другого агента, получает предел вызова инструмента — 25 шагов.
AGENT_RECURSION_LIMIT = 10000

# Инструменты, без которых агент не прочитает разогрев и не запишет черновик.
REQUIRED_TOOL_NAMES = (READ_TOOL_NAME, WRITE_TOOL_NAME, EDIT_TOOL_NAME, DELETE_TOOL_NAME)


def run_agent(
    *,
    role: AgentRole,
    task: str,
    input_dirs: tuple[Path, ...],
    project_path: str,
    private_dir_name: Path,
    extra_readable_dirs: tuple[Path, ...],
    extra_writable_dirs: tuple[Path, ...],
    extra_command_writable_dirs: tuple[Path, ...],
    extra_tools: tuple[BaseTool, ...],
    shell_processes: ShellProcesses,
    journal_path: Path,
    settings: Settings,
) -> Path:
    """
    Запускает агента роли на задаче и ждёт окончания работы.

        role: роль агента.
        task: задача агенту.
        input_dirs: папки результатов других агентов: агент их читает в разогреве.
        project_path: папка рабочего проекта.
        private_dir_name: путь личной папки агента внутри папки личных папок.
        extra_readable_dirs: папки, где агенту разрешено чтение в фазе работы, кроме личной папки
            и папок результатов других агентов; с папкой проекта агент видит её в разогреве.
        extra_writable_dirs: папки, где агенту разрешена запись в фазе работы, кроме черновика
            и файла контекста.
        extra_command_writable_dirs: дополнительный доступ на запись только для команд bash и start_service
            и запущенных ими программ, к папкам из extra_writable_dirs; файловым инструментам write, edit
            и delete запись туда не открывается. Пустой кортеж - команды пишут туда же, куда файловые инструменты.
        extra_tools: инструменты, собранные вне ядра агента: помощники-агенты, инструменты серверов MCP;
            в фазе черновика вместо них заглушки с отказом. Почему отдельно: в этих инструментах сидят другие агенты-помощники
            и передать их стандартно не получится: будет циклическая зависимость
        shell_processes: учёт фоновых процессов команд bash и start_service агента; процессы снимаются,
            когда агент закончит работу.
        journal_path: файл журнала агента.
        settings: настройки приложения.

    Возвращает: Папку черновика агента: его результат.
    """
    chat_model: BaseChatModel = build_chat_model(
        config = OllamaConfig(
            base_url = settings.ollama_base_url,
            model = role.model_name,
            context_window = settings.agent_ctx_window
        ),
        # выключенное размышление — параметры выборки режима без размышления
        generation_mode = (
            GenerationMode.NON_THINKING if role.reasoning_level is ReasoningLevel.NONE else GenerationMode.THINKING
        ),
        reasoning_level = role.reasoning_level,
    )

    project_dir = Path(project_path).resolve()
    private_dir = project_dir / PRIVATE_ROOT / private_dir_name
    relative_private_dir = private_dir.relative_to(project_dir)

    # Личная папка с папкой черновика создаётся до запуска агента
    draft_dir(private_dir = private_dir).mkdir(parents = True, exist_ok = True)

    # Просмотренный файлы - одинаковые для фазы работы и фазы черновика
    seen_files = SeenFiles()
    # Отказы файловых инструментов по пути за шаг - одни для фазы работы и фазы черновика
    path_refusals = PathRefusals()

    _check_required_tools(tool_names = role.tool_names)

    # Фаза работы
    workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        input_dirs = input_dirs,
        readable_dirs = (private_dir, helpers_dir(private_dir = private_dir), *input_dirs, *extra_readable_dirs),
        writable_dirs = (private_dir, *extra_writable_dirs),
    )
    # Рабочее место команд bash и start_service: папки записи фазы работы и папки, открытые только командам
    command_workspace = replace(workspace, writable_dirs = (*workspace.writable_dirs, *extra_command_writable_dirs))
    # Хозяин команд агента: одна песочница на все команды bash и службы агента
    command_host = CommandHost(write_roots = command_workspace.writable_dirs, processes = shell_processes)
    # Остановка фоновых процессов агента: одна и та же в фазе работы и в фазе черновика
    stop_process_tool = build_stop_process_tool(processes = shell_processes)
    tools = _build_tools(
        builders = {
            **file_tool_builders(workspace = workspace, seen_files = seen_files, refusals = path_refusals),
            BASH_TOOL_NAME: lambda: build_bash_tool(
                workspace = command_workspace, processes = shell_processes, host = command_host
            ),
            START_SERVICE_TOOL_NAME: lambda: build_start_service_tool(
                workspace = command_workspace, processes = shell_processes, host = command_host
            ),
            STOP_PROCESS_TOOL_NAME: lambda: stop_process_tool,
        },
        tool_names = role.tool_names,
    ) + list(extra_tools)

    # Фаза черновика. Писать можно только в личную папку. Остальные тулы должны быть запрещены
    # TODO запрет должен касаться и тулов вызова других агентов, а также web-code-ресерчей
    draft_workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        input_dirs = (),
        readable_dirs = (private_dir, helpers_dir(private_dir = private_dir)),
        writable_dirs = (private_dir,),
    )
    # тот же набор инструментов, но с другими ограничениями
    draft_tools = _build_tools(
        builders = {
            **file_tool_builders(workspace = draft_workspace, seen_files = seen_files, refusals = path_refusals),
            BASH_TOOL_NAME: lambda: build_disabled_bash_tool(
                refusal = DRAFT_PHASE_BASH_REFUSAL.format(
                    draft_dir = draft_dir(private_dir = relative_private_dir),
                    context_file_path = context_path(private_dir = relative_private_dir),
                )
            ),
            START_SERVICE_TOOL_NAME: lambda: build_disabled_start_service_tool(refusal = DRAFT_PHASE_START_SERVICE_REFUSAL),
            STOP_PROCESS_TOOL_NAME: lambda: stop_process_tool,
        },
        tool_names = role.tool_names,
    ) + [
        build_disabled_tool(tool = tool, refusal = DRAFT_PHASE_HELPER_TOOL_REFUSAL.format(tool_name = tool.name))
        for tool in extra_tools
    ]

    agent = create_agent_graph(tools = tools, draft_tools = draft_tools)
    bound_chat_model = chat_model.bind_tools(tools)

    system_instructions = AGENT_SYSTEM_INSTRUCTIONS.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        draft_rules = build_draft_rules(
            answer_files = role.answer_files,
            shown_draft_dir = draft_dir(private_dir = relative_private_dir).as_posix(),
        ),
        context_file_path = context_path(private_dir = relative_private_dir),
        context_file_name = CONTEXT_FILE_NAME,
    )
    limit_notice = LIMIT_NOTICE.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        context_file_path = context_path(private_dir = relative_private_dir),
        context_file_name = CONTEXT_FILE_NAME,
    )
    reinit_notice = REINIT_NOTICE.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        context_file_path = context_path(private_dir = relative_private_dir),
    )
    empty_draft_notice = EMPTY_DRAFT_NOTICE.format(draft_dir = draft_dir(private_dir = relative_private_dir))

    # Корень проекта: чтение в разогреве, если агенту разрешено читать папку проекта
    reads_project = project_dir in (folder.resolve() for folder in extra_readable_dirs)
    project_root_reads = [(READ_TOOL_NAME, {"file_path": "."})] if reads_project else []

    # Правила проекта: блок в системном промпте и чтение файла в разогреве, если файл есть и проект читается
    has_project_rules = reads_project and (project_dir / PROJECT_RULES_FILE_NAME).is_file()
    project_rules_instructions = (
        PROJECT_RULES_INSTRUCTIONS.format(project_rules_file = PROJECT_RULES_FILE_NAME) if has_project_rules else ""
    )
    project_rules_reads = [(READ_TOOL_NAME, {"file_path": PROJECT_RULES_FILE_NAME})] if has_project_rules else []

    # Документация проекта: чтение списка файлов папки в разогреве, если папка есть и проект читается
    has_project_docs = reads_project and (project_dir / PROJECT_DOCS_DIR_NAME).is_dir()
    project_docs_reads = [(READ_TOOL_NAME, {"file_path": PROJECT_DOCS_DIR_NAME})] if has_project_docs else []

    # Статистика запуска: события графа и явные счётчики, файл рядом с журналом
    statistics = AgentStatistics(
        role_name = role.name,
        journal_name = journal_path.stem,
        model_name = role.model_name,
        reasoning_level = role.reasoning_level.value,
        context_window = settings.agent_ctx_window,
        tool_names = [tool.name for tool in tools],
    )

    # Сегодняшняя дата: одна на всю работу агента
    today_instructions = TODAY_INSTRUCTIONS.format(today = date.today().isoformat())

    # Кодовое имя агента: путь его личной папки
    code_name_instructions = CODE_NAME_INSTRUCTIONS.format(code_name = private_dir_name.as_posix())

    config = RunnableConfig(
        recursion_limit = AGENT_RECURSION_LIMIT,
        configurable = {
            AGENT_CFG_NAME: AgentConfig(
                system_prompt = (
                    role.system_prompt
                    + system_instructions
                    + project_rules_instructions
                    + today_instructions
                    + code_name_instructions
                ),
                task = task,
                chat_model = bound_chat_model,
                warmup_calls = [
                    *project_root_reads,
                    *project_rules_reads,
                    *project_docs_reads,
                    *_input_reads(project_dir = project_dir, input_dirs = input_dirs),
                ],
                history_token_limit = 60000,
                soft_limit_extra_steps = 2,
                history_token_hard_limit = 90000,
                context_window_limit = settings.agent_ctx_window - RESPONSE_TOKEN_RESERVE,
                max_resets = 10,
                limit_notice = limit_notice,
                reinit_notice = reinit_notice,
                empty_draft_notice = empty_draft_notice,
                step_hooks = role.step_hooks,
                answer_checks = role.answer_checks,
                relative_private_dir = relative_private_dir,
                project_dir = project_dir,
                seen_files = seen_files,
                path_refusals = path_refusals,
                shell_processes = shell_processes,
                statistics = statistics,
            )
        }
    )

    initial_state = AgentState(
        messages = [],
        reset_count = 0,
        answer_notices = 0,
        repeats = INITIAL_REPEAT_STATE,
        soft_limit_steps = 0,
    )
    journal = AgentJournal(path = journal_path, agent_name = role.name, model_name = role.model_name)
    journal.write_tools(tools = bound_chat_model.kwargs["tools"])
    try:
        for event in agent.stream(input = initial_state, config = config):
            journal.write(event = event)
            statistics.record(event = event)
    except Exception as error:
        journal.write_error(error = error)
        statistics.fail(error = error)
        raise
    finally:
        shell_processes.kill_all()
        command_host.close()
        statistics.write(path = journal_path.with_suffix(STATISTICS_FILE_SUFFIX))

    journal.finish()

    return draft_dir(private_dir = private_dir)


def _check_required_tools(*, tool_names: tuple[str, ...]) -> None:
    """
    Проверяет, что в списке инструментов роли есть обязательные инструменты.

        tool_names: имена инструментов роли.
    """
    missing_names = [name for name in REQUIRED_TOOL_NAMES if name not in tool_names]
    if missing_names:
        raise ValueError(f"в инструментах роли нет обязательных: {', '.join(missing_names)}")


def _build_tools(*, builders: dict[str, Callable[[], BaseTool]], tool_names: tuple[str, ...]) -> list[BaseTool]:
    """
    Собирает инструменты фазы с именами из списка роли.

        builders: сборщики инструментов фазы по именам инструментов.
        tool_names: имена инструментов роли.

    Возвращает: Инструменты в порядке списка роли.
    """
    unknown_names = [name for name in tool_names if name not in builders]
    if unknown_names:
        raise ValueError(f"неизвестные инструменты роли: {', '.join(unknown_names)}")

    return [builders[name]() for name in tool_names]


def _input_reads(*, project_dir: Path, input_dirs: tuple[Path, ...]) -> list[tuple[str, dict]]:
    """
    Собирает вызовы разогрева, читающие результаты других агентов.

        project_dir: папка проекта.
        input_dirs: папки результатов других агентов.

    Возвращает: Вызовы read: список файлов каждой папки и каждый её файл по порядку имён.
    """
    calls = []
    for input_dir in input_dirs:
        relative_dir = input_dir.relative_to(project_dir)
        calls.append((READ_TOOL_NAME, {"file_path": str(relative_dir)}))
        calls.extend(
            (READ_TOOL_NAME, {"file_path": str(relative_dir / section.name)})
            for section in sorted(input_dir.glob("*.md"))
        )

    return calls
