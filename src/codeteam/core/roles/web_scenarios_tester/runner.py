"""Прогон сценариев в браузере: запуск приложения, помощник с браузером на каждый сценарий, наблюдения в файлы."""

import logging
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException

from codeteam.common.git import UNTRACKED_STATUS, list_uncommitted_changes, restore_paths
from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import PRIVATE_ROOT, Workspace
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.browser_checker import check_app_url, run_browser_checker
from codeteam.core.roles.common import CallerContext
from codeteam.core.roles.web_scenarios import AppLaunch
from codeteam.core.roles.web_scenarios_tester.prompts import HELPER_FAILED_OBSERVATIONS, LAUNCH_FAILED_OBSERVATIONS
from codeteam.core.tools.shell import START_SERVICE_TOOL_NAME, build_start_service_tool

logger = logging.getLogger(__name__)

# Папка наблюдений внутри личной папки проверки по сценариям: файл на сценарий, под именем файла сценария.
OBSERVATIONS_DIR_NAME = "observations"

# Файл наблюдений, когда приложение не запустилось.
LAUNCH_FAILED_FILE_NAME = "000_launch_failed.md"

# Порты адреса без явного порта.
DEFAULT_PORTS = {"http": 80, "https": 443}

# Предел ожидания готовности приложения, секунды.
APP_READY_TIMEOUT_SECONDS = 60


def run_scenarios(
    *,
    cfg: PipelineConfig,
    caller_name: str,
    private_dir_name: Path,
    journal_name: str,
    launch: AppLaunch,
    scenario_paths: list[Path],
) -> Path:
    """
    Запускает приложение и по очереди отдаёт каждый сценарий отдельному помощнику с браузером. Наблюдения
    помощника пишутся в файл под именем файла сценария; помощник упал — в файл пишется ошибка.
    Приложение не запустилось — сценарии не проходятся, в папке один файл LAUNCH_FAILED_FILE_NAME.
    После прогона процессы приложения останавливаются, а правки проекта, появившиеся за прогон, убираются:
    отслеживаемые файлы возвращаются к коммиту, новые файлы удаляются.

        cfg: настройки запуска пайплайна.
        caller_name: имя роли, от которой просят проверку.
        private_dir_name: личная папка роли внутри папки личных папок; папки помощников лежат рядом с ней.
        journal_name: журнал роли без расширения; журналы помощников называются от него.
        launch: команда запуска и адрес приложения.
        scenario_paths: файлы сценариев по порядку прохождения.

    Возвращает: Папку наблюдений.
    """
    project_dir = Path(cfg.project_path).resolve()
    private_dir = project_dir / PRIVATE_ROOT / private_dir_name
    observations_dir = private_dir / OBSERVATIONS_DIR_NAME
    observations_dir.mkdir(parents = True, exist_ok = True)
    workspace = Workspace(
        project_dir = project_dir,
        private_dir = private_dir,
        input_dirs = (),
        readable_dirs = (private_dir,),
        writable_dirs = (private_dir, project_dir),
    )
    changes_before = set(list_uncommitted_changes(project_dir = project_dir))
    processes = ShellProcesses()
    host = CommandHost(write_roots = workspace.writable_dirs, processes = processes)
    try:
        launch_error = _start_app(workspace = workspace, processes = processes, host = host, launch = launch)
        if launch_error is not None:
            logger.warning(f"[{caller_name}] приложение не запустилось: {launch.command}")
            (observations_dir / LAUNCH_FAILED_FILE_NAME).write_text(
                LAUNCH_FAILED_OBSERVATIONS.format(command = launch.command, url = launch.url, error = launch_error),
                encoding = "utf-8",
            )
            return observations_dir

        caller_context = CallerContext(
            cfg = cfg,
            caller_name = caller_name,
            caller_private_dir_name = private_dir_name,
            caller_journal_name = journal_name,
            shell_processes = processes,
        )
        for scenario_path in scenario_paths:
            logger.info(f"[{caller_name}] сценарий {scenario_path.name}")
            observations = _check_scenario(
                caller_context = caller_context,
                project_dir = project_dir,
                url = launch.url,
                scenario_path = scenario_path,
            )
            (observations_dir / scenario_path.name).write_text(observations, encoding = "utf-8")
    finally:
        processes.kill_all()
        host.close()
        _remove_run_changes(project_dir = project_dir, changes_before = changes_before, caller_name = caller_name)

    return observations_dir


def _start_app(*, workspace: Workspace, processes: ShellProcesses, host: CommandHost, launch: AppLaunch) -> str | None:
    """
    Запускает приложение инструментом start_service и ждёт, пока оно ответит по адресу.

        workspace: рабочее место запуска.
        processes: учёт фоновых процессов прогона.
        host: хозяин команд прогона.
        launch: команда запуска и адрес приложения.

    Возвращает: Текст ошибки запуска; None, если приложение отвечает по адресу.
    """
    parsed = urlparse(launch.url)
    start_service = build_start_service_tool(workspace = workspace, processes = processes, host = host)
    answer: ToolMessage = start_service.invoke({
        "type": "tool_call",
        "id": "start_app",
        "name": START_SERVICE_TOOL_NAME,
        "args": {
            "command": launch.command,
            "port": parsed.port or DEFAULT_PORTS[parsed.scheme],
            "timeout_seconds": APP_READY_TIMEOUT_SECONDS,
        },
    })
    if answer.status == "error":
        return answer.text

    try:
        check_app_url(url = launch.url, processes = processes)
    except ToolException as error:
        return f"{answer.text}\n\n{error}"

    return None


def _check_scenario(*, caller_context: CallerContext, project_dir: Path, url: str, scenario_path: Path) -> str:
    """
    Отдаёт один сценарий помощнику с браузером.

        caller_context: роль, от которой просят проверку.
        project_dir: папка проекта.
        url: адрес запущенного приложения.
        scenario_path: файл сценария.

    Возвращает: Наблюдения помощника; если он упал или не записал наблюдения — текст ошибки.
    """
    try:
        observations_path = run_browser_checker(
            caller_context = caller_context,
            project_dir = project_dir,
            url = url,
            scenarios = scenario_path.read_text(encoding = "utf-8", errors = "replace"),
        )
    except ToolException as error:
        return HELPER_FAILED_OBSERVATIONS.format(error = error)

    return observations_path.read_text(encoding = "utf-8", errors = "replace")


def _remove_run_changes(*, project_dir: Path, changes_before: set[tuple[str, str]], caller_name: str) -> None:
    """
    Убирает правки проекта, появившиеся за прогон: отслеживаемые файлы возвращает к коммиту, новые файлы удаляет.

        project_dir: папка проекта.
        changes_before: незакоммиченные правки до прогона, их не трогает.
        caller_name: имя роли для лога.
    """
    run_changes = [
        change for change in list_uncommitted_changes(project_dir = project_dir) if change not in changes_before
    ]
    tracked_paths = tuple(path for status, path in run_changes if status != UNTRACKED_STATUS)
    if tracked_paths:
        restore_paths(project_dir = project_dir, paths = tracked_paths)
    for status, path in run_changes:
        if status == UNTRACKED_STATUS:
            (project_dir / path).unlink(missing_ok = True)
    if run_changes:
        logger.info(f"[{caller_name}] убраны правки проекта за прогон: {', '.join(path for _, path in run_changes)}")
