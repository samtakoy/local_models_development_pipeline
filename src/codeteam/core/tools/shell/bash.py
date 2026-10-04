"""Инструмент агента bash: команда оболочки в папке проекта.

Команды не учитывают правила пропуска файлов (common.files.ignore) и ограничения чтения рабочего
места: агент читает любой файл, например `cat .env`. Требует доработки.
"""

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import run_command
from codeteam.core.agent.workspace import Workspace

# Предел времени команды, если агент его не задал, секунды.
BASH_TIMEOUT_SECONDS = 120

# Наибольший предел времени, который может задать агент, секунды.
BASH_TIMEOUT_LIMIT_SECONDS = 600

# Сколько последних символов вывода команды видит агент.
BASH_OUTPUT_LIMIT = 30_000

BASH_DESCRIPTION = """Выполняет команду bash в папке проекта и возвращает код возврата и вывод
(stdout и stderr вместе).

Инструмент для команд терминала: тесты, git, uv, python.
Для работы с файлами используй отдельные инструменты когда они доступны:
- поиск файлов: glob
- поиск по содержимому: grep
- чтение файлов: read
- правка файлов: edit
- запись файлов: write
- сообщения: пиши текстом в ответе (не echo, printf)


Правила:
- Пути с пробелами бери в двойные кавычки: python "/path/with spaces/script.py".
- Независимые команды запускай несколькими вызовами bash в одном ответе.
- Зависимые команды соединяй через && в одном вызове: git add . && git commit -m "msg".
- Не разделяй команды переводом строки (внутри кавычек можно).

Ограничения:
- Ввода с клавиатуры нет: команды, которые ждут ввода, не запускай.
- Длинный вывод обрезается: видны последние 30000 символов.
- Команда прерывается по истечении timeout_seconds."""


# Имя инструмента команд оболочки.
BASH_TOOL_NAME = "bash"


class BashArguments(BaseModel):
    """
    Аргументы bash.
    """

    command: str = Field(description = "команда bash")
    timeout_seconds: int | None = Field(
        default = None,
        description = "предел времени в секундах, по умолчанию 120, не больше 600",
    )


def build_bash_tool(*, workspace: Workspace) -> BaseTool:
    """
    Собирает инструмент bash для рабочего места вызова.

    Команда запускается в папке проекта. На macOS запись разрешена только в папки записи рабочего
    места и временные папки системы; на других системах bash без ограничений.

        workspace: рабочее место вызова.

    Возвращает: Инструмент bash.
    """

    def bash(*, command: str, timeout_seconds: int | None = None) -> str:
        """
        Выполняет команду для агента.

            command: команда bash.
            timeout_seconds: предел времени в секундах.

        Возвращает: Код возврата и вывод команды. Ошибку для агента поднимает ToolException.
        """
        timeout = BASH_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        if not 1 <= timeout <= BASH_TIMEOUT_LIMIT_SECONDS:
            raise ToolException(f"Ошибка: timeout_seconds должен быть от 1 до {BASH_TIMEOUT_LIMIT_SECONDS}")

        result = run_command(
            command = command,
            working_dir = str(workspace.project_dir),
            timeout_seconds = timeout,
            write_roots = workspace.writable_dirs,
        )
        if result.exit_code is None:
            raise ToolException(
                f"Ошибка: команда прервана, превышен предел времени {timeout} с\n"
                + _tail(output = result.output)
            )

        return f"Код возврата: {result.exit_code}\n{_tail(output = result.output)}"

    return StructuredTool.from_function(
        func = bash,
        name = BASH_TOOL_NAME,
        description = BASH_DESCRIPTION,
        args_schema = BashArguments,
        handle_tool_error = True,
    )



def build_disabled_bash_tool(*, refusal: str) -> BaseTool:
    """
    Собирает заглушку bash: то же имя и описание, но любая команда получает отказ.

        refusal: текст отказа для агента.

    Возвращает: Инструмент bash, который не выполняет команды.
    """

    def bash(*, command: str, timeout_seconds: int | None = None) -> str:
        """
        Отказывает в выполнении команды.

            command: команда bash.
            timeout_seconds: предел времени в секундах.

        Возвращает: Ничего не возвращает: отказ для агента поднимает ToolException.
        """
        raise ToolException(refusal)

    return StructuredTool.from_function(
        func = bash,
        name = BASH_TOOL_NAME,
        description = BASH_DESCRIPTION,
        args_schema = BashArguments,
        handle_tool_error = True,
    )


def _tail(*, output: str) -> str:
    """
    Оставляет конец вывода в пределах BASH_OUTPUT_LIMIT.

        output: полный вывод команды.

    Возвращает: Вывод целиком или его конец с пометкой об обрезке.
    """
    if len(output) <= BASH_OUTPUT_LIMIT:
        return output

    return (
        f"(Начало вывода обрезано: всего символов {len(output)}, показаны последние {BASH_OUTPUT_LIMIT})\n"
        + output[-BASH_OUTPUT_LIMIT:]
    )
