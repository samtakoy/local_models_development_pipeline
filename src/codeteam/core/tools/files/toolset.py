"""Наборы файловых инструментов вызова с общими виденными файлами и правилами пропуска."""

from langchain_core.tools import BaseTool

from codeteam.common.files import IgnoreRules, load_ignore_rules
from codeteam.core.agent.workspace import CLOSED_NAMES, Workspace
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files.glob import build_glob_tool
from codeteam.core.tools.files.grep import build_grep_tool
from codeteam.core.tools.files.read import build_read_tool
from codeteam.core.tools.files.edit import build_edit_tool
from codeteam.core.tools.files.write import build_write_tool

# Служебные папки и файлы, которые поиск glob и grep пропускает на любой глубине;
# запись в виде правил .gitignore.
SEARCH_SKIPPED_NAMES = (
    ".git/",
    ".venv/",
    "venv/",
    "node_modules/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".idea/",
    ".DS_Store",
)


def build_file_tools(*, workspace: Workspace, seen_files: SeenFiles) -> list[BaseTool]:
    """
    Собирает инструменты read, glob, grep, write и edit для рабочего места вызова.

    Инструменты делят виденные файлы: write и edit меняют существующий файл,
    только если вызов читал его и файл с тех пор не менялся.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов, общие для всех наборов инструментов агента.

    Возвращает: Инструменты read, glob, grep, write, edit.
    """
    ignore_rules = _workspace_ignore_rules(workspace = workspace)

    return [
        build_read_tool(workspace = workspace, seen_files = seen_files, ignore_rules = ignore_rules),
        build_glob_tool(workspace = workspace, ignore_rules = ignore_rules),
        build_grep_tool(workspace = workspace, ignore_rules = ignore_rules),
        build_write_tool(workspace = workspace, seen_files = seen_files, ignore_rules = ignore_rules),
        build_edit_tool(workspace = workspace, seen_files = seen_files),
    ]

def build_read_tools(*, workspace: Workspace) -> list[BaseTool]:
    ignore_rules = _workspace_ignore_rules(workspace = workspace)
    return [
        build_read_tool(workspace = workspace, seen_files = SeenFiles(), ignore_rules = ignore_rules),
        build_glob_tool(workspace = workspace, ignore_rules = ignore_rules),
        build_grep_tool(workspace = workspace, ignore_rules = ignore_rules),
    ]


def _workspace_ignore_rules(*, workspace: Workspace) -> IgnoreRules:
    """
    Собирает правила пропуска проекта; личная папка вызова от правил открыта.

        workspace: рабочее место вызова.

    Возвращает: Правила пропуска.
    """
    return load_ignore_rules(
        project_dir = workspace.project_dir,
        closed_names = CLOSED_NAMES,
        search_skipped_names = SEARCH_SKIPPED_NAMES,
        open_dirs = (workspace.private_dir,),
    )
