"""Инструмент агента bash: команда оболочки в папке проекта.

Команды выполняются через хозяина команд агента (CommandHost): в песочнице запись разрешена только в
папки записи рабочего места, сигналы — только процессам агента. Чтение не ограничивается.
"""

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import CommandHost, CommandHostRestarted, ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell._internal.output_file import new_output_file

# Предел времени команды, если агент его не задал, секунды.
BASH_TIMEOUT_SECONDS = 120

# Наибольший предел времени, который может задать агент, секунды.
BASH_TIMEOUT_LIMIT_SECONDS = 600

# Сколько последних символов вывода команды видит агент.
BASH_OUTPUT_LIMIT = 10_000

# Папка полного вывода обрезанных команд внутри папки временных файлов проверки CHECK_DIR.
BASH_OUTPUT_DIR_NAME = "bash_output"

BASH_DESCRIPTION = f"""Выполняет команду bash в папке проекта и возвращает код возврата и вывод
(stdout и stderr вместе).

Инструмент для команд терминала: тесты, git, uv, python.
Для работы с файлами используй отдельные инструменты когда они доступны:
- поиск файлов: glob — вместо find и ls
- поиск по содержимому: grep — вместо grep и rg в bash
- чтение файлов: read — вместо cat, head, tail
- правка файлов: edit — вместо sed, awk
- запись файлов: write — вместо echo > и cat <<EOF
- сообщения: пиши текстом в ответе (не echo, printf)


Правила:
- Пути с пробелами бери в двойные кавычки: python "/path/with spaces/script.py".
- Независимые команды запускай несколькими вызовами bash в одном ответе.
- Зависимые команды соединяй через && в одном вызове: git add . && git commit -m "msg".
- Не разделяй команды переводом строки (внутри кавычек можно).

Ограничения:
- Каждый вызов — новая оболочка: cd, export и source между вызовами не сохраняются.
  Нужное окружение и переменные задавай в той же команде через &&.
- Фоновые процессы (&) продолжают работать между вызовами и завершаются, когда ты закончишь работу.
  Вызов их не ждёт: вывод фонового процесса после конца вызова пропадает, поэтому перенаправляй его в файл.
  Сервер или службу запускай инструментом start_service: он дождётся готовности и покажет ошибку старта.
- Отказ «Operation not permitted» при kill значит, что процесс не твой: остановить можно только свои процессы.
- ps недоступен: список процессов — pgrep -fl; свои фоновые процессы останавливай инструментом stop_process.
- Ввода с клавиатуры нет: команды, которые ждут ввода, не запускай.
- Длинный вывод обрезается: видны последние {BASH_OUTPUT_LIMIT} символов, полный вывод сохраняется в файл, путь — в ответе.
- Команда прерывается по истечении timeout_seconds."""

# Часть описания bash о рабочем месте вызова: папка запуска, папки записи и закрытое для чтения.
BASH_WORKSPACE_DESCRIPTION = """

Рабочее место:
- Команда запускается в папке проекта {project_dir}: cd в неё не нужен, пути пиши относительно неё.
- Запись разрешена только в: {writable_dirs} и во временные папки системы.
  Отказ «Operation not permitted» или «Permission denied» при записи значит, что путь вне этих папок."""

# Отказ bash, если процесс-хозяин команд упал и запущен заново.
BASH_HOST_RESTARTED_REFUSAL = (
    "Ошибка: оболочка перезапущена, команда не выполнена. Твои фоновые процессы остановлены. "
    "Повтори команду."
)


# Код команды, которую остановил сигнал SIGPIPE: следующая команда цепочки перестала читать вывод.
SIGPIPE_EXIT_CODE = 141

# Имя инструмента команд оболочки.
BASH_TOOL_NAME = "bash"


class BashArguments(BaseModel):
    """
    Аргументы bash.
    """

    command: str = Field(description = "команда bash")
    timeout_seconds: int | None = Field(
        default = None,
        description = f"предел времени в секундах, по умолчанию {BASH_TIMEOUT_SECONDS}, не больше {BASH_TIMEOUT_LIMIT_SECONDS}",
    )


def build_bash_tool(*, workspace: Workspace, processes: ShellProcesses, host: CommandHost) -> BaseTool:
    """
    Собирает инструмент bash для рабочего места вызова.

    Команда запускается в папке проекта через хозяина команд агента. Описание инструмента называет
    папку запуска и папки записи.

        workspace: рабочее место вызова.
        processes: учёт фоновых процессов команд; их снимает владелец учёта.
        host: хозяин команд агента: выполняет команду в песочнице агента.

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

        try:
            result = host.run(command = command, working_dir = str(workspace.project_dir), timeout_seconds = timeout)
        except CommandHostRestarted as error:
            raise ToolException(BASH_HOST_RESTARTED_REFUSAL) from error

        processes.remember(
            process_group_id = result.process_group_id,
            background_process_id = result.background_process_id,
            command = command,
        )
        if result.exit_code is None:
            raise ToolException(
                f"Ошибка: команда прервана, превышен предел времени {timeout} с.\n"
                f"Если команда должна работать дольше и не ждёт ввода с клавиатуры, повтори её с большим "
                f"timeout_seconds.\n"
                + _shown_output(output = result.output, workspace = workspace)
            )

        lines = [f"Код возврата: {result.exit_code}"]
        pipe_line = _pipe_line(pipe_exit_codes = result.pipe_exit_codes)
        if pipe_line is not None:
            lines.append(pipe_line)
        lines.append(_shown_output(output = result.output, workspace = workspace))

        return "\n".join(lines)

    description = BASH_DESCRIPTION + BASH_WORKSPACE_DESCRIPTION.format(
        project_dir = workspace.project_dir,
        writable_dirs = workspace.show_folders(folders = workspace.writable_dirs),
    )

    return StructuredTool.from_function(
        func = bash,
        name = BASH_TOOL_NAME,
        description = description,
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


def _pipe_line(*, pipe_exit_codes: tuple[int, ...]) -> str | None:
    """
    Собирает строку с кодами команд цепочки через |.

        pipe_exit_codes: коды команд последней цепочки.

    Возвращает: Строку с кодами, если в цепочке больше одной команды и хотя бы одна вернула не 0;
        иначе None.
    """
    if len(pipe_exit_codes) < 2 or not any(pipe_exit_codes):
        return None

    line = "Коды команд цепочки через |: " + " ".join(str(code) for code in pipe_exit_codes)
    if SIGPIPE_EXIT_CODE in pipe_exit_codes:
        line += f" ({SIGPIPE_EXIT_CODE} — следующая команда перестала читать вывод, для head это нормально)"

    return line


def _shown_output(*, output: str, workspace: Workspace) -> str:
    """
    Готовит вывод команды для агента: длинный вывод сохраняет в файл и оставляет последние целые строки
    в пределах BASH_OUTPUT_LIMIT символов.

        output: полный вывод команды.
        workspace: рабочее место вызова: в его папке CHECK_DIR сохраняется полный вывод.

    Возвращает: Вывод целиком или пометку об обрезке с путём к полному выводу и конец вывода.
    """
    if len(output) <= BASH_OUTPUT_LIMIT:
        return output

    output_path = new_output_file(workspace = workspace, dir_name = BASH_OUTPUT_DIR_NAME, prefix = "output_")
    output_path.write_text(output, encoding = "utf-8")
    full_output = (
        f"Полный вывод: {workspace.display_path(path = output_path)} — "
        f"читать инструментом read (offset, limit) или искать инструментом grep."
    )

    lines = output.split("\n")
    if lines[-1] == "":
        lines.pop()
    shown_lines = _last_lines(lines = lines, limit = BASH_OUTPUT_LIMIT)

    if not shown_lines:
        return (
            f"Вывод обрезан: показан конец строки {len(lines)} из {len(lines)}. {full_output}\n"
            + lines[-1][-BASH_OUTPUT_LIMIT:]
        )

    first_shown = len(lines) - len(shown_lines) + 1
    return (
        f"Вывод обрезан: показаны строки {first_shown}–{len(lines)} из {len(lines)}. {full_output}\n"
        + "\n".join(shown_lines)
    )


def _last_lines(*, lines: list[str], limit: int) -> list[str]:
    """
    Берёт последние целые строки, которые вместе с переводами строк укладываются в limit символов.

        lines: строки вывода.
        limit: предел символов.

    Возвращает: Последние строки по порядку; пустой список, если последняя строка длиннее предела.
    """
    shown_lines: list[str] = []
    size = 0
    for line in reversed(lines):
        size += len(line) + 1
        if size > limit:
            break
        shown_lines.append(line)

    shown_lines.reverse()

    return shown_lines
