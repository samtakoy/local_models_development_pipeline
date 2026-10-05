"""Инструмент агента stop_process: остановка фоновых процессов, запущенных агентом через bash."""

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import ShellProcess, ShellProcesses

# Имя инструмента остановки фоновых процессов.
STOP_PROCESS_TOOL_NAME = "stop_process"

STOP_PROCESS_DESCRIPTION = """Останавливает фоновый процесс, который ты запустил через bash.

Через bash (kill, pkill, killall) можно остановить только процесс, запущенный в том же вызове bash.
Процесс из прошлого вызова останавливай этим инструментом.
Чужие процессы остановить нельзя: ни через bash, ни этим инструментом.

Аргументы:
- pid: номер процесса. Выводи его при запуске: команда > файл 2>&1 & echo $!
  Не указан — остановить все твои фоновые процессы.

Останавливается процесс и всё, что запущено с ним в том же вызове bash."""


class StopProcessArguments(BaseModel):
    """
    Аргументы stop_process.
    """

    pid: int | None = Field(
        default = None,
        description = "номер процесса; не указан - остановить все твои фоновые процессы",
    )


def build_stop_process_tool(*, processes: ShellProcesses) -> BaseTool:
    """
    Собирает инструмент остановки фоновых процессов агента.

        processes: учёт фоновых процессов команд bash агента.

    Возвращает: Инструмент stop_process.
    """

    def stop_process(*, pid: int | None = None) -> str:
        """
        Останавливает фоновый процесс агента или все его фоновые процессы.

            pid: номер процесса; None - все фоновые процессы агента.

        Возвращает: Итог остановки. Отказ для агента поднимает ToolException.
        """
        if pid is None:
            alive = processes.alive_processes()
            processes.kill_all()
            if not alive:
                return "Работающих фоновых процессов не было."

            return "Остановлены процессы:\n" + _show_processes(processes = alive)

        if not processes.kill_group_of(process_id = pid):
            raise ToolException(_refusal(pid = pid, alive = processes.alive_processes()))

        return f"Остановлен процесс {pid} и всё, что запущено с ним в том же вызове bash."

    return StructuredTool.from_function(
        func = stop_process,
        name = STOP_PROCESS_TOOL_NAME,
        description = STOP_PROCESS_DESCRIPTION,
        args_schema = StopProcessArguments,
        handle_tool_error = True,
    )


def _refusal(*, pid: int, alive: list[ShellProcess]) -> str:
    """
    Собирает отказ для номера, которого нет среди фоновых процессов агента.

        pid: номер процесса из вызова.
        alive: работающие фоновые процессы агента.

    Возвращает: Текст отказа со списком работающих фоновых процессов агента.
    """
    refusal = f"Ошибка: процесса {pid} нет среди твоих работающих фоновых процессов."
    if not alive:
        return refusal + " Работающих фоновых процессов у тебя нет."

    return (
        refusal
        + " Твои фоновые процессы:\n"
        + _show_processes(processes = alive)
        + "\nВызови stop_process с номером из списка или без pid, чтобы остановить все."
    )


def _show_processes(*, processes: list[ShellProcess]) -> str:
    """
    Показывает процессы строками «номер: команда».

        processes: процессы.

    Возвращает: Строки процессов через перевод строки.
    """
    return "\n".join(f"- {process.process_id}: {process.command}" for process in processes)
