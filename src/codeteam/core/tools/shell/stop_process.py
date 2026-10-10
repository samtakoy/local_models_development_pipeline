"""Инструмент агента stop_process: остановка фоновых процессов, запущенных агентом через bash."""

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import ShellProcess, ShellProcesses
from codeteam.core.tools.shell.stop_process_prompts import (
    STOP_PROCESS_DESCRIPTION,
    STOP_PROCESS_LINE,
    STOP_PROCESS_NONE_RUNNING,
    STOP_PROCESS_PID_DESCRIPTION,
    STOP_PROCESS_STOPPED_ALL,
    STOP_PROCESS_STOPPED_ONE,
    STOP_PROCESS_UNKNOWN_ERROR,
    STOP_PROCESS_UNKNOWN_WITH_LIST_ERROR,
)
from codeteam.core.tools.shell.tool_names import STOP_PROCESS_TOOL_NAME


class StopProcessArguments(BaseModel):
    """
    Аргументы stop_process.
    """

    pid: int | None = Field(default = None, description = STOP_PROCESS_PID_DESCRIPTION)


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
            processes.kill_background()
            if not alive:
                return STOP_PROCESS_NONE_RUNNING

            return STOP_PROCESS_STOPPED_ALL.format(processes = _show_processes(processes = alive))

        if not processes.kill_group_of(process_id = pid):
            raise ToolException(_refusal(pid = pid, alive = processes.alive_processes()))

        return STOP_PROCESS_STOPPED_ONE.format(pid = pid)

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
    if not alive:
        return STOP_PROCESS_UNKNOWN_ERROR.format(pid = pid)

    return STOP_PROCESS_UNKNOWN_WITH_LIST_ERROR.format(pid = pid, processes = _show_processes(processes = alive))


def _show_processes(*, processes: list[ShellProcess]) -> str:
    """
    Показывает процессы строками «номер: команда».

        processes: процессы.

    Возвращает: Строки процессов через перевод строки.
    """
    return "\n".join(
        STOP_PROCESS_LINE.format(process_id = process.process_id, command = process.command)
        for process in processes
    )
