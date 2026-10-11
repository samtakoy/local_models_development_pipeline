"""Пути от агента для файловых инструментов: проверка доступа и маски путей."""

import re
from pathlib import Path

from langchain_core.tools import ToolException
from pathspec import GitIgnoreSpec

from codeteam.common.files import IgnoreRules
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files.common_prompts import FILE_NOT_FOUND_ERROR, HIDDEN_PATH_ERROR, PATH_ACCESS_ERROR
from codeteam.core.tools.files.refusals import PathRefusal, PathRefusals

# Группа в фигурных скобках без вложенных скобок внутри.
_BRACE_GROUP_PATTERN = re.compile(r"\{([^{}]*)\}")


def resolve_visible_path(
    *,
    workspace: Workspace,
    ignore_rules: IgnoreRules,
    refusals: PathRefusals,
    path: str,
) -> Path:
    """
    Переводит путь от агента в абсолютный и проверяет, что агенту можно его видеть.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.
        refusals: отказы по пути за шаг агента.
        path: путь от агента, абсолютный или относительно папки проекта.

    Возвращает: Существующий путь внутри папок чтения, не закрытый правилами.
        Ошибку для агента поднимает ToolException.
    """
    try:
        resolved = workspace.resolve_readable(path = path)
    except PathOutsideWorkspace as error:
        raise path_refusal_error(
            error = error,
            refusal = PathRefusal(path = path, is_write = False),
            refusals = refusals,
        ) from error

    refuse_hidden_path(workspace = workspace, ignore_rules = ignore_rules, path = resolved)
    if not resolved.exists():
        shown_path = workspace.display_path(path = resolved)
        raise ToolException(FILE_NOT_FOUND_ERROR.format(shown_path = shown_path))

    return resolved


def path_refusal_error(
    *,
    error: PathOutsideWorkspace,
    refusal: PathRefusal,
    refusals: PathRefusals,
) -> ToolException:
    """
    Запоминает отказ по пути и собирает ошибку для агента.

        error: отказ рабочего места.
        refusal: отказ по пути.
        refusals: отказы по пути за шаг агента.

    Возвращает: Ошибку с текстом отказа.
    """
    refusals.add(refusal = refusal)

    return ToolException(PATH_ACCESS_ERROR.format(error = error))


def refuse_hidden_path(*, workspace: Workspace, ignore_rules: IgnoreRules, path: Path) -> None:
    """
    Отказывает, если путь закрыт правилами пропуска проекта.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.
        path: абсолютный путь с раскрытыми ссылками.

    Ошибку для агента поднимает ToolException.
    """
    if ignore_rules.is_closed(path = path):
        shown_path = workspace.display_path(path = path)
        raise ToolException(HIDDEN_PATH_ERROR.format(shown_path = shown_path))


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
