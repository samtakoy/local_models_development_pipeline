from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from codeteam.app.settings import Settings
from codeteam.common.llm import build_chat_model, OllamaConfig, GenerationMode, ReasoningLevel
from codeteam.core.agent.config import AgentConfig
from codeteam.core.agent.graph import create_agent_graph, AgentState, AGENT_CFG_NAME
from codeteam.core.agent.journal import AgentJournal
from codeteam.core.agent.prompts import DRAFT_PHASE_HINT, CONTEXT_FILE_NAME, AGENT_SYSTEM_INSTRUCTIONS, LIMIT_NOTICE, \
    REINIT_NOTICE, draft_dir, context_path
from codeteam.core.agent.workspace import Workspace, PRIVATE_ROOT
from codeteam.core.tools.files import READ_TOOL_NAME, build_file_tools, SeenFiles


def run_agent(
    agent_name: str,
    system_prompt: str,
    model_name: str,
    task: str,
    project_path: str,
    journal_path: Path,
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

    project_dir = Path(project_path).resolve()
    private_dir = project_dir / PRIVATE_ROOT / agent_name
    relative_private_dir = private_dir.relative_to(project_dir)

    # Просмотренный файлы - одинаковые для фазы работы и фазы черновика
    seen_files = SeenFiles()

    # Фаза работы. TODO писать черновик могу все, но нужен список тулов свой для каждого агента
    workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        readable_dirs = (project_dir,),
        # отдельно укажем папку и файл
        # writable_dirs = (private_dir,),
        writable_dirs = (
            draft_dir(private_dir = private_dir),
            context_path(private_dir = private_dir),
        ),
        refusal_hint = None
    )
    tools = build_file_tools(workspace = workspace, seen_files = seen_files)

    # Фаза черновика. Писать можно только в личную папку. Остальные тулы должны быть запрещены
    # TODO запрет должен касаться и тулов вызова других агентов, а также web-code-ресерчей
    draft_workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        readable_dirs = (private_dir,),
        # отдельно укажем папку и файл
        # writable_dirs = (private_dir,),
        writable_dirs = (
            draft_dir(private_dir = private_dir),
            context_path(private_dir = private_dir),
        ),
        refusal_hint = DRAFT_PHASE_HINT.format(
            private_dir = relative_private_dir,
            context_file_path = CONTEXT_FILE_NAME
        ),
    )
    # тот де набор инструментов, но с другими ограничениями
    draft_tools = build_file_tools(workspace = draft_workspace, seen_files = seen_files)

    agent = create_agent_graph(tools = tools, draft_tools = draft_tools)

    system_instructions = AGENT_SYSTEM_INSTRUCTIONS.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        context_file_path = context_path(private_dir = relative_private_dir),
        context_file_name = CONTEXT_FILE_NAME,
    )
    limit_notice = LIMIT_NOTICE.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        context_file_path = context_path(private_dir = relative_private_dir),
    )
    reinit_notice = REINIT_NOTICE.format(
        draft_dir = draft_dir(private_dir = relative_private_dir),
        context_file_path = context_path(private_dir = relative_private_dir),
    )

    config = RunnableConfig(
        configurable = {
            AGENT_CFG_NAME: AgentConfig(
                system_prompt = system_prompt + system_instructions,
                task = task,
                chat_model = chat_model.bind_tools(tools),
                warmup_calls = [
                    # читаем заранее корневую папку проекта за агента
                    (READ_TOOL_NAME, {"file_path": "."})
                ],
                history_token_limit = 30000,
                max_resets = 10,
                limit_notice = limit_notice,
                reinit_notice = reinit_notice,
                relative_private_dir = relative_private_dir,
                project_dir = project_dir,
            )
        }
    )

    initial_state = AgentState(messages = [], reset_count = 0)
    journal = AgentJournal(path = journal_path, agent_name = agent_name, model_name = model_name)
    try:
        for event in agent.stream(input = initial_state, config = config):
            journal.write(event = event)
    except Exception as error:
        journal.write_error(error = error)
        raise

    journal.finish()

