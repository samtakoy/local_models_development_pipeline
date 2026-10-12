"""Тесты прогрева сервера документации: проверка ключа Context7 при старте."""

from pathlib import Path

import pytest
from langchain_core.tools import StructuredTool

from codeteam.core.roles.advisor import documentation
from codeteam.core.roles.advisor.documentation import RESOLVE_LIBRARY_FOUND, RESOLVE_LIBRARY_TOOL_NAME, \
    warm_up_documentation
from codeteam.core.roles.common import PipelineError


def _resolve_tool(*, answer: str) -> StructuredTool:
    """
    Собирает заглушку resolve-library-id с заданным ответом.

        answer: ответ заглушки.

    Возвращает: Инструмент с именем resolve-library-id.
    """

    def resolve(query: str, libraryName: str) -> str:
        """Возвращает заданный ответ."""
        return answer

    return StructuredTool.from_function(func = resolve, name = RESOLVE_LIBRARY_TOOL_NAME, description = "заглушка")


def test_key_check_without_key_is_rejected(tmp_path: Path) -> None:
    """Проверка ключа включена, а ключа нет — прогон не начинается, сервер не запускается."""
    with pytest.raises(PipelineError):
        warm_up_documentation(
            work_dir = tmp_path / "warm_up",
            npm_cache_dir = tmp_path / "npm",
            api_key = None,
            check_key = True,
        )

    assert not (tmp_path / "warm_up").exists()


def test_found_libraries_pass_key_probe() -> None:
    """Пробный поиск нашёл библиотеки — ключ подошёл."""
    tool = _resolve_tool(answer = f"{RESOLVE_LIBRARY_FOUND}\n\n- Title: Flask")

    assert documentation._probe_key(resolve_tool = tool) is None


def test_key_error_fails_key_probe() -> None:
    """Сервер ответил ошибкой ключа — проверка возвращает его ответ."""
    tool = _resolve_tool(answer = "Invalid API key. Please check your API key.")

    assert documentation._probe_key(resolve_tool = tool) == "Invalid API key. Please check your API key."
