"""Пути от агента для файловых инструментов: проверка доступа и маски путей."""

import re
from pathlib import Path

from langchain_core.tools import ToolException
from pathspec import GitIgnoreSpec

from codeteam.common.files import IgnoreRules
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files._hints import PATH_HINT

# Группа в фигурных скобках без вложенных скобок внутри.
_BRACE_GROUP_PATTERN = re.compile(r"\{([^{}]*)\}")


def resolve_visible_path(*, workspace: Workspace, ignore_rules: IgnoreRules, path: str) -> Path:
    """
    Переводит путь от агента в абсолютный и проверяет, что агенту можно его видеть.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.
        path: путь от агента, абсолютный или относительно папки проекта.

    Возвращает: Существующий путь внутри папок чтения, не скрытый правилами.
        Ошибку для агента поднимает ToolException.
    """
    try:
        resolved = workspace.resolve_readable(path = path)
    except PathOutsideWorkspace as error:
        raise ToolException(f"Ошибка: {error}") from error

    refuse_hidden_path(workspace = workspace, ignore_rules = ignore_rules, path = resolved)
    if not resolved.exists():
        shown_path = workspace.display_path(path = resolved)
        raise ToolException(f"Ошибка: файл не найден: {shown_path}. {PATH_HINT}")

    return resolved


def refuse_hidden_path(*, workspace: Workspace, ignore_rules: IgnoreRules, path: Path) -> None:
    """
    Отказывает, если путь скрыт правилами пропуска проекта.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.
        path: абсолютный путь с раскрытыми ссылками.

    Ошибку для агента поднимает ToolException.
    """
    if ignore_rules.is_ignored(path = path):
        shown_path = workspace.display_path(path = path)
        raise ToolException(
            f"Ошибка: {shown_path} закрыт: его скрывают правила проекта (служебные имена и .gitignore)"
        )


def compile_path_mask(*, mask: str) -> GitIgnoreSpec:
    """
    Разбирает маску пути в правило вида .gitignore: маска без косой черты сверяется с именем
    файла на любой глубине, `**` — любое число папок, `{a,b}` — любой из вариантов.

        mask: маска от агента, например "*.py", "src/**/*.ts" или "*.{ts,tsx}".

    Возвращает: Правило для сверки с путём относительно папки поиска.
    """
    return GitIgnoreSpec.from_lines(_expand_braces(mask = mask))


def _expand_braces(*, mask: str) -> list[str]:
    """
    Раскрывает фигурные скобки маски в отдельные маски, вложенные скобки — изнутри наружу.

        mask: маска, например "*.{ts,tsx}".

    Возвращает: Маски без фигурных скобок, например ["*.ts", "*.tsx"]; маску без пары скобок — как есть.
    """
    group = _BRACE_GROUP_PATTERN.search(mask)
    if group is None:
        return [mask]

    expanded_masks = []
    for variant in group.group(1).split(","):
        expanded_masks.extend(_expand_braces(mask = mask[:group.start()] + variant + mask[group.end():]))

    return expanded_masks
