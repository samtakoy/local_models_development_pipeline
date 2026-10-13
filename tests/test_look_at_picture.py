"""Тесты инструмента describe_picture: нет модели - нет инструмента, ошибки пути, запрос к смотрящей модели."""

import base64
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from codeteam.app.settings import Settings
from codeteam.common.shell import ShellProcesses
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.common import CallerContext
from codeteam.core.roles.picture_viewer import build_describe_picture_tool
from codeteam.core.roles.picture_viewer import tool as tool_module

# Содержимое картинки теста: байты не обязаны быть настоящим PNG, модель подменена.
PICTURE_BYTES = b"\x89PNG fake picture"

# Описание, которое возвращает подменённая модель.
DESCRIPTION = "Сверху синяя шапка с надписью «Библиотека»."


class FakeVisionModel:
    """
    Заглушка смотрящей модели: запоминает сообщения и возвращает описание.
    """

    def __init__(self) -> None:
        self.messages: list = []

    def invoke(self, messages: list) -> AIMessage:
        """
        Запоминает сообщения запроса.

            messages: сообщения запроса.

        Возвращает: Ответ с описанием картинки.
        """
        self.messages = messages

        return AIMessage(content = DESCRIPTION)


def _caller_context(*, project_dir: Path, vision_model: str | None) -> CallerContext:
    """
    Собирает агента-спрашивающего с настройками смотрящей модели.

        project_dir: папка проекта.
        vision_model: смотрящая модель; None - не задана.

    Возвращает: Агента, для которого собирается инструмент.
    """
    settings = Settings(
        ollama_base_url = "http://127.0.0.1:11434",
        agent_model = "qwen3.5:9b",
        agent_ctx_window = 32000,
        max_output_tokens = 32000,
        history_token_limit = 60000,
        history_token_hard_limit = 90000,
        response_token_reserve = 16000,
        runs_dir = project_dir / "runs",
        prompts_db_dir = project_dir / "prompts_db",
        workspaces_dir = project_dir / "workspaces",
        vision_model = vision_model,
        vision_ctx_window = 16000,
        browser_headless = True,
        context7_api_key = None,
        context7_check_key_at_start = False,
        npm_cache_dir = project_dir / ".npm-cache",
        playwright_mcp_environment = {},
    )

    return CallerContext(
        cfg = PipelineConfig(
            project_path = str(project_dir),
            run_dir = project_dir / "runs" / "run",
            model_name = "model",
            roles = (),
            browser_check = False,
            library_docs = False,
            settings = settings,
        ),
        caller_name = "pm",
        caller_private_dir_name = Path("pm_r1"),
        caller_journal_name = "01_pm_r1",
        shell_processes = ShellProcesses(),
    )


@pytest.fixture
def vision_model(monkeypatch: pytest.MonkeyPatch) -> FakeVisionModel:
    """
    Подменяет сборку клиента модели заглушкой смотрящей модели.

    Возвращает: Заглушку модели.
    """
    fake = FakeVisionModel()
    monkeypatch.setattr(tool_module, "build_chat_model", lambda **arguments: fake)

    return fake


@pytest.fixture
def picture_tool(tmp_path: Path, vision_model: FakeVisionModel) -> BaseTool:
    """
    Инструмент describe_picture в папке проекта теста с картинкой docs/design/main.png.

    Возвращает: Инструмент.
    """
    picture = tmp_path / "project" / "docs" / "design" / "main.png"
    picture.parent.mkdir(parents = True)
    picture.write_bytes(PICTURE_BYTES)
    (tmp_path / "project" / "notes.txt").write_text("заметки\n", encoding = "utf-8")

    return build_describe_picture_tool(_caller_context(project_dir = tmp_path / "project", vision_model = "qwen3.5:9b"))


def test_no_vision_model_no_tool(tmp_path: Path) -> None:
    """
    Смотрящая модель не задана - инструмента нет.
    """
    assert build_describe_picture_tool(_caller_context(project_dir = tmp_path, vision_model = None)) is None


def test_picture_is_described(picture_tool: BaseTool, vision_model: FakeVisionModel) -> None:
    """
    Картинка уходит в модель вместе с тем, на что обратить внимание; описание модели возвращается.
    """
    answer = picture_tool.invoke({"file_path": "docs/design/main.png", "focus": "цвет шапки"})

    assert answer == DESCRIPTION
    request = vision_model.messages[-1].content
    assert "цвет шапки" in request[0]["text"]
    assert request[1]["base64"] == base64.b64encode(PICTURE_BYTES).decode("ascii")
    assert request[1]["mime_type"] == "image/png"


@pytest.mark.parametrize("file_path", ["docs/design/missing.png", "../outside.png", "notes.txt"])
def test_bad_path_does_not_call_model(picture_tool: BaseTool, vision_model: FakeVisionModel, file_path: str) -> None:
    """
    Нет файла, путь вне проекта или не картинка - модель не вызывается, агент получает ошибку.
    """
    answer = picture_tool.invoke({"file_path": file_path})

    assert vision_model.messages == []
    assert answer != DESCRIPTION
