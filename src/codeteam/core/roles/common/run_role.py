"""Запуск агента роли в пайплайне."""

from pathlib import Path

from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.run_agent import run_agent
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.common.external_tools import CallerContext
from codeteam.core.roles.common.role_settings import RoleSettings
from codeteam.core.tools.mcp import McpTools


def run_role(
    *,
    cfg: PipelineConfig,
    role: RoleSettings,
    journal_name: str,
    task: str,
    input_dirs: tuple[Path, ...],
    private_dir_name: Path,
    extra_readable_dirs: tuple[Path, ...],
    extra_writable_dirs: tuple[Path, ...],
    extra_command_writable_dirs: tuple[Path, ...],
) -> Path:
    """
    Запускает агента роли и ждёт его результата. Внешние инструменты из описания роли собираются под этот
    запуск: помощникам и серверам MCP нужны папка и журнал агента. Сессии серверов MCP открыты,
    пока агент работает.

        cfg: настройки запуска пайплайна.
        role: описание роли.
        journal_name: имя журнала агента без расширения.
        task: задача агенту.
        input_dirs: папки результатов других агентов.
        private_dir_name: путь личной папки агента внутри папки личных папок.
        extra_readable_dirs: папки чтения агента в фазе работы, кроме личной папки и папок результатов
            других агентов.
        extra_writable_dirs: папки записи агента в фазе работы, кроме черновика и файла контекста.
        extra_command_writable_dirs: дополнительный доступ на запись только для команд bash и start_service
            и запущенных ими программ, к папкам из extra_writable_dirs; файловым инструментам write, edit
            и delete запись туда не открывается. Пустой кортеж - команды пишут туда же, куда файловые инструменты.

    Возвращает: Папку черновика агента.
    """
    agent_role = AgentRole(
        name = role.name,
        system_prompt = _load_system_prompt(path = role.system_prompt_path, fields = role.prompt_fields),
        model_name = role.model_name if role.model_name is not None else cfg.model_name,
        reasoning_level = role.reasoning_level,
        tool_names = role.tool_names,
        step_hooks = role.step_hooks,
        step_checks = role.step_checks,
        answer_checks = role.answer_checks,
    )

    caller_context = CallerContext(
        cfg = cfg,
        caller_name = role.name,
        caller_private_dir_name = private_dir_name,
        caller_journal_name = journal_name,
    )
    helper_tools = [
        tool for build_tool in role.helper_tools if (tool := build_tool(caller_context)) is not None
    ]
    mcp_servers = tuple(build_server(caller_context) for build_server in role.mcp_servers)
    with McpTools(servers = mcp_servers) as mcp_tools:
        return run_agent(
            role = agent_role,
            task = task,
            input_dirs = input_dirs,
            project_path = cfg.project_path,
            private_dir_name = private_dir_name,
            extra_readable_dirs = extra_readable_dirs,
            extra_writable_dirs = extra_writable_dirs,
            extra_command_writable_dirs = extra_command_writable_dirs,
            extra_tools = (*helper_tools, *mcp_tools),
            journal_path = cfg.run_dir / f"{journal_name}.md",
            settings = cfg.settings,
        )


def make_journal_name(*, journal_count: int, private_dir_name: Path) -> str:
    """
    Строит имя журнала следующего агента прогона по его личной папке.

        journal_count: число журналов агентов, уже начатых в прогоне.
        private_dir_name: путь личной папки агента внутри папки личных папок.

    Возвращает: Имя журнала без расширения, например 04_stage_100_senior_r1.
    """
    return f"{journal_count + 1:02d}_{'_'.join(private_dir_name.parts)}"


def _load_system_prompt(*, path: Path, fields: dict[str, str]) -> str:
    """
    Читает системный промпт роли и подставляет в него поля.

        path: файл системного промпта.
        fields: значения полей вида {имя поля} в тексте промпта.

    Возвращает: Текст системного промпта.
    """
    return path.read_text(encoding = "utf-8").strip().format(**fields)
