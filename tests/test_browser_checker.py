"""Тесты инструмента check_in_browser: проверка адреса до запуска помощника, папки и журналы помощника, ответ, предел."""

import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.core.agent.workspace import PRIVATE_ROOT, draft_dir
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.browser_checker import OBSERVATIONS_FILE_NAME, build_check_in_browser_tool
from codeteam.core.roles.browser_checker import tool as tool_module
from codeteam.core.roles.browser_checker.tool import BROWSER_CHECK_CALL_LIMIT
from codeteam.core.roles.common import CallerContext

# Личная папка и журнал спрашивающего агента.
CALLER_DIR_NAME = Path("stage_10/developer_review_r1")
CALLER_JOURNAL_NAME = "12_stage_10_developer_review_r1"

# Наблюдения, которые пишет заглушка помощника.
OBSERVATIONS = "Открыл главную: видна таблица.\n"


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


@pytest.fixture
def fake_run_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeRunRole:
    """
    Подменяет запуск помощника заглушкой.

    Возвращает: Заглушку запуска роли.
    """
    fake = FakeRunRole(project_dir = tmp_path)
    monkeypatch.setattr(tool_module, "run_role", fake)

    return fake


@pytest.fixture
def check_tool(tmp_path: Path) -> BaseTool:
    """
    Инструмент check_in_browser приёмщика этапа в папке проекта теста.

    Возвращает: Инструмент.
    """
    caller_context = CallerContext(
        cfg = PipelineConfig(
            project_path = str(tmp_path),
            run_dir = tmp_path / "run",
            model_name = "model",
            roles = (),
            settings = None,
        ),
        caller_name = "developer_review",
        caller_private_dir_name = CALLER_DIR_NAME,
        caller_journal_name = CALLER_JOURNAL_NAME,
    )

    return build_check_in_browser_tool(caller_context)


@pytest.fixture
def app_url() -> Iterator[str]:
    """
    Запускает тестовый сервер, который отвечает ошибкой 500.

    Возвращает: Адрес сервера.
    """
    server = HTTPServer(("127.0.0.1", 0), ErrorPageHandler)
    thread = threading.Thread(target = server.serve_forever, daemon = True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def _free_port() -> int:
    """
    Находит порт, который никто не слушает.

    Возвращает: Номер порта.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


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
    answer = _check(tool = check_tool, url = f"http://127.0.0.1:{_free_port()}/")

    assert fake_run_role.calls == []
    assert answer != OBSERVATIONS


def test_running_app_starts_helper(check_tool: BaseTool, fake_run_role: FakeRunRole, app_url: str) -> None:
    """
    Приложение отвечает, пусть и ошибкой 500, - помощник запускается в новой папке внутри папки спросившего,
    его наблюдения возвращаются.
    """
    first = _check(tool = check_tool, url = app_url)
    second = _check(tool = check_tool, url = app_url)

    assert first == OBSERVATIONS
    assert second == OBSERVATIONS
    assert [call["private_dir_name"] for call in fake_run_role.calls] == [
        CALLER_DIR_NAME / "browser_checker_r1",
        CALLER_DIR_NAME / "browser_checker_r2",
    ]
    assert [call["journal_name"] for call in fake_run_role.calls] == [
        f"{CALLER_JOURNAL_NAME}.browser_checker_r1",
        f"{CALLER_JOURNAL_NAME}.browser_checker_r2",
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
