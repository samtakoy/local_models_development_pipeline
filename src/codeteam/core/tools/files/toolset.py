"""Наборы файловых инструментов вызова с общими виденными файлами и правилами пропуска."""

from langchain_core.tools import BaseTool

from codeteam.common.files import IgnoreRules, load_ignore_rules
from codeteam.core.agent.workspace import IGNORED_NAMES, Workspace
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files.glob import build_glob_tool
from codeteam.core.tools.files.grep import build_grep_tool
from codeteam.core.tools.files.read import build_read_tool
from codeteam.core.tools.files.edit import build_edit_tool
from codeteam.core.tools.files.write import build_write_tool


def build_file_tools(*, workspace: Workspace) -> list[BaseTool]:
    """
    Собирает инструменты read, glob, grep, write и edit для рабочего места вызова.

    Инструменты делят виденные файлы: write и edit меняют существующий файл,
    только если вызов читал его и файл с тех пор не менялся.

        workspace: рабочее место вызова.

    Возвращает: Инструменты read, glob, grep, write, edit.
    """
    seen_files = SeenFiles()
    ignore_rules = _workspace_ignore_rules(workspace = workspace)

    return [
        build_read_tool(workspace = workspace, seen_files = seen_files, ignore_rules = ignore_rules),
        build_glob_tool(workspace = workspace, ignore_rules = ignore_rules),
        build_grep_tool(workspace = workspace, ignore_rules = ignore_rules),
        build_write_tool(workspace = workspace, seen_files = seen_files, ignore_rules = ignore_rules),
        build_edit_tool(workspace = workspace, seen_files = seen_files),
    ]


def _workspace_ignore_rules(*, workspace: Workspace) -> IgnoreRules:
    """
    Собирает правила пропуска проекта; личная папка вызова от правил открыта.

        workspace: рабочее место вызова.

    Возвращает: Правила пропуска.
    """
    return load_ignore_rules(
        project_dir = workspace.project_dir,
        ignored_names = IGNORED_NAMES,
        open_dirs = (workspace.private_dir,),
    )
