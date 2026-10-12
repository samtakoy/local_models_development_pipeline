"""Тесты инструмента check_in_browser: проверка адреса до запуска помощника, папки и журналы помощника, ответ, предел."""

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError

from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.browser_checker import OBSERVATIONS_FILE_NAME, build_check_in_browser_tool
from codeteam.core.roles.browser_checker import tool as tool_module
from codeteam.core.roles.browser_checker.tool import BROWSER_CHECK_CALL_LIMIT
from codeteam.core.roles.common import CallerContext
from tests.shell_helpers import error_page_server_command, free_port, requires_sandbox, wait_port_open

# Личная папка и журнал спрашивающего агента.
CALLER_DIR_NAME = Path("s10/developer_review_r1")

# Папка помощников спрашивающего агента: рядом с его личной папкой.
CALLER_HELPERS_DIR_NAME = Path("s10/developer_review_r1_help")
CALLER_JOURNAL_NAME = "12_s10_developer_review_r1"

# Наблюдения, которые пишет заглушка помощника.
OBSERVATIONS = "Открыл главную: видна таблица.\n"

# Предел времени команды приёмщика в тестах, секунды.
COMMAND_TIMEOUT_SECONDS = 20

# Сколько инструмент ждёт запуска приложения в тестах, секунды.
TEST_APP_START_WAIT_SECONDS = 2

# Через сколько запускается приложение, которое поднимается с задержкой, секунды.
APP_START_DELAY_SECONDS = 1


class ErrorPageHandler(BaseHTTPRequestHandler):
    """
    Обработчик тестового сервера: на любой запрос отвечает ошибкой 500, как сломанная страница приложения.
    """

    def do_GET(self) -> None:
        """Отвечает ошибкой 500."""
        self.send_response(500)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Не пишет запросы в вывод теста."""


class FakeRunRole:
    """
    Заглушка запуска роли: записывает вызовы и кладёт наблюдения в черновик помощника.
    """

    def __init__(self, *, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.calls: list[dict] = []

    def __call__(self, **arguments) -> Path:
        """
        Кладёт наблюдения в черновик личной папки помощника.

            arguments: аргументы run_role.

        Возвращает: Папку черновика.
        """
        self.calls.append(arguments)
        answer_dir = draft_dir(private_dir = self.project_dir / PRIVATE_ROOT / arguments["private_dir_name"])
        answer_dir.mkdir(parents = True, exist_ok = True)
        (answer_dir / OBSERVATIONS_FILE_NAME).write_text(OBSERVATIONS, encoding = "utf-8")

        return answer_dir


@pytest.fixture(autouse = True)
def short_app_start_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Сокращает ожидание запуска приложения, чтобы тесты молчащего порта шли быстро.
    """
    monkeypatch.setattr(tool_module, "APP_START_WAIT_SECONDS", TEST_APP_START_WAIT_SECONDS)


@pytest.fixture
def fake_run_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeRunRole:
    """
    Подменяет запуск помощника заглушкой.

    Возвращает: Заглушку запуска роли.
    """
    fake = FakeRunRole(project_dir = tmp_path)
    monkeypatch.setattr(tool_module, "run_role", fake)

    return fake


def _caller_context(*, project_dir: Path, browser_check: bool, processes: ShellProcesses) -> CallerContext:
    """
    Собирает приёмщика этапа, который просит проверку в браузере.

        project_dir: папка проекта.
        browser_check: проверка в браузере из файла состава.
        processes: учёт фоновых процессов приёмщика.

    Возвращает: Агента, для которого собирается инструмент.
    """
    return CallerContext(
        cfg = PipelineConfig(
            project_path = str(project_dir),
            run_dir = project_dir / "run",
            model_name = "model",
            roles = (),
            browser_check = browser_check,
            library_docs = False,
            settings = None,
        ),
        caller_name = "developer_review",
        caller_private_dir_name = CALLER_DIR_NAME,
        caller_journal_name = CALLER_JOURNAL_NAME,
        shell_processes = processes,
    )


@pytest.fixture
def processes() -> Iterator[ShellProcesses]:
    """
    Учёт фоновых процессов приёмщика; после теста все процессы снимаются.

    Возвращает: Учёт фоновых процессов.
    """
    shell_processes = ShellProcesses()
    yield shell_processes
    shell_processes.kill_all()


@pytest.fixture
def check_tool(tmp_path: Path, processes: ShellProcesses) -> BaseTool:
    """
    Инструмент check_in_browser приёмщика этапа в папке проекта теста.

    Возвращает: Инструмент.
    """
    return build_check_in_browser_tool(_caller_context(project_dir = tmp_path, browser_check = True, processes = processes))


def test_browser_check_off_no_tool(tmp_path: Path, processes: ShellProcesses) -> None:
    """
    Проверка в браузере выключена - инструмента нет.
    """
    caller_context = _caller_context(project_dir = tmp_path, browser_check = False, processes = processes)

    assert build_check_in_browser_tool(caller_context) is None


@pytest.fixture
def host(tmp_path: Path, processes: ShellProcesses) -> Iterator[CommandHost]:
    """
    Хозяин команд приёмщика с тем же учётом процессов, что у инструмента.

    Возвращает: Хозяин команд; останавливается после теста.
    """
    command_host = CommandHost(write_roots = (tmp_path,), processes = processes)
    yield command_host
    command_host.close()


def _start_app(*, host: CommandHost, processes: ShellProcesses, work_dir: Path, detached: bool) -> str:
    """
    Запускает приложение приёмщика его командой: отвечает ошибкой 500.

        host: хозяин команд приёмщика.
        processes: учёт фоновых процессов приёмщика.
        work_dir: папка запуска.
        detached: приложение уходит в фон в новой сессии.

    Возвращает: Адрес приложения.
    """
    port = free_port()
    command = error_page_server_command(port = port, detached = detached)
    result = host.run(command = command, working_dir = str(work_dir), timeout_seconds = COMMAND_TIMEOUT_SECONDS)
    processes.remember(
        process_group_id = result.process_group_id,
        background_process_id = result.background_process_id,
        command = command,
    )
    assert wait_port_open(port = port)

    return f"http://127.0.0.1:{port}/"


@pytest.fixture
def app_url(host: CommandHost, processes: ShellProcesses, tmp_path: Path) -> str:
    """
    Запускает приложение приёмщика в фоне через &.

    Возвращает: Адрес приложения.
    """
    return _start_app(host = host, processes = processes, work_dir = tmp_path, detached = False)


@pytest.fixture
def foreign_url() -> Iterator[str]:
    """
    Запускает сервер чужой программы: работает в процессе теста, в учёт приёмщика не входит.

    Возвращает: Адрес сервера.
    """
    server = HTTPServer(("127.0.0.1", 0), ErrorPageHandler)
    thread = threading.Thread(target = server.serve_forever, daemon = True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def _check(*, tool: BaseTool, url: str) -> str:
    """
    Вызывает инструмент со сценарием.

        tool: инструмент check_in_browser.
        url: адрес приложения.

    Возвращает: Ответ инструмента.
    """
    return tool.invoke({"url": url, "scenarios": "Открыть главную, увидеть таблицу."})


def test_not_local_url_does_not_start_helper(check_tool: BaseTool, fake_run_role: FakeRunRole) -> None:
    """
    Адрес не на этом компьютере - помощник не запускается.
    """
    answer = _check(tool = check_tool, url = "https://example.com/")

    assert fake_run_role.calls == []
    assert answer != OBSERVATIONS


def test_silent_port_does_not_start_helper(check_tool: BaseTool, fake_run_role: FakeRunRole) -> None:
    """
    На порту никто не слушает - помощник не запускается.
    """
    answer = _check(tool = check_tool, url = f"http://127.0.0.1:{free_port()}/")

    assert fake_run_role.calls == []
    assert answer != OBSERVATIONS


def test_foreign_app_does_not_start_helper(
    check_tool: BaseTool,
    fake_run_role: FakeRunRole,
    foreign_url: str,
) -> None:
    """
    По адресу отвечает программа, которую приёмщик не запускал, - помощник не запускается.
    """
    answer = _check(tool = check_tool, url = foreign_url)

    assert fake_run_role.calls == []
    assert answer != OBSERVATIONS


@requires_sandbox
def test_detached_app_starts_helper(
    check_tool: BaseTool,
    fake_run_role: FakeRunRole,
    host: CommandHost,
    processes: ShellProcesses,
    tmp_path: Path,
) -> None:
    """
    Приложение приёмщика ушло в фон в новой сессии - оно всё равно его, помощник запускается.
    """
    url = _start_app(host = host, processes = processes, work_dir = tmp_path, detached = True)

    answer = _check(tool = check_tool, url = url)

    assert answer == OBSERVATIONS


@requires_sandbox
def test_app_starting_late_starts_helper(
    check_tool: BaseTool,
    fake_run_role: FakeRunRole,
    host: CommandHost,
    tmp_path: Path,
) -> None:
    """
    Приложение начинает принимать соединения через секунду после вызова - инструмент дожидается его
    и запускает помощника.
    """
    port = free_port()
    server = error_page_server_command(port = port, detached = True)
    host.run(
        command = f"(sleep {APP_START_DELAY_SECONDS}; {server}) > /dev/null 2>&1 &",
        working_dir = str(tmp_path),
        timeout_seconds = COMMAND_TIMEOUT_SECONDS,
    )

    answer = _check(tool = check_tool, url = f"http://127.0.0.1:{port}/")

    assert answer == OBSERVATIONS


def test_helper_failure_returns_error_to_caller(
    check_tool: BaseTool,
    app_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Помощник упал - спросивший получает ошибку ответом инструмента, а не исключение.
    """
    def failing_run_role(**arguments) -> Path:
        """Падает, как помощник, исчерпавший предел шагов графа."""
        raise GraphRecursionError("предел шагов")

    monkeypatch.setattr(tool_module, "run_role", failing_run_role)

    answer = _check(tool = check_tool, url = app_url)

    assert "GraphRecursionError" in answer


def test_running_app_starts_helper(
    check_tool: BaseTool,
    fake_run_role: FakeRunRole,
    app_url: str,
    tmp_path: Path,
) -> None:
    """
    Приложение отвечает, пусть и ошибкой 500, - помощник запускается в новой папке внутри папки помощников
    спросившего, а не в его личной папке; наблюдения возвращаются.
    """
    first = _check(tool = check_tool, url = app_url)
    second = _check(tool = check_tool, url = app_url)

    assert first == OBSERVATIONS
    assert second == OBSERVATIONS
    assert [call["private_dir_name"] for call in fake_run_role.calls] == [
        CALLER_HELPERS_DIR_NAME / "bro_check_r1",
        CALLER_HELPERS_DIR_NAME / "bro_check_r2",
    ]
    assert not (tmp_path / PRIVATE_ROOT / CALLER_DIR_NAME).exists()
    assert [call["journal_name"] for call in fake_run_role.calls] == [
        f"{CALLER_JOURNAL_NAME}.bro_check_r1",
        f"{CALLER_JOURNAL_NAME}.bro_check_r2",
    ]
    assert app_url in fake_run_role.calls[0]["task"]


def test_call_limit(check_tool: BaseTool, fake_run_role: FakeRunRole, app_url: str) -> None:
    """
    После BROWSER_CHECK_CALL_LIMIT вызовов помощник больше не запускается; отказы по адресу предел не тратят.
    """
    _check(tool = check_tool, url = "https://example.com/")
    for _ in range(BROWSER_CHECK_CALL_LIMIT):
        assert _check(tool = check_tool, url = app_url) == OBSERVATIONS

    answer = _check(tool = check_tool, url = app_url)

    assert len(fake_run_role.calls) == BROWSER_CHECK_CALL_LIMIT
    assert answer != OBSERVATIONS


def test_parallel_calls_run_one_at_a_time(
    check_tool: BaseTool,
    fake_run_role: FakeRunRole,
    app_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Два вызова одновременно: помощники работают по очереди, оба ответа возвращаются.
    """
    running = {"now": 0, "most": 0}
    counter_lock = threading.Lock()
    original_call = fake_run_role.__call__

    def slow_run_role(**arguments) -> Path:
        """Считает одновременно работающих помощников и держит каждого немного дольше."""
        with counter_lock:
            running["now"] += 1
            running["most"] = max(running["most"], running["now"])
        time.sleep(0.2)
        answer_dir = original_call(**arguments)
        with counter_lock:
            running["now"] -= 1

        return answer_dir

    monkeypatch.setattr(tool_module, "run_role", slow_run_role)
    answers: list[str] = []
    threads = [
        threading.Thread(target = lambda: answers.append(_check(tool = check_tool, url = app_url)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert answers == [OBSERVATIONS, OBSERVATIONS]
    assert running["most"] == 1
    assert len(fake_run_role.calls) == 2
