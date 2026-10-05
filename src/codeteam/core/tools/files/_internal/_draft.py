"""Правила файлов в папке черновика: только разделы ответа, файл контекста — рядом."""

from pathlib import Path

from codeteam.core.agent.workspace import DRAFT_SECTION_PATTERN, Workspace
from codeteam.core.tools.files._hints import CONTEXT_IN_DRAFT_REFUSAL, NOT_DRAFT_SECTION_REFUSAL


def draft_file_refusal(*, workspace: Workspace, path: Path) -> str | None:
    """
    Проверяет файл, который агент записывает в папку черновика.

        workspace: рабочее место вызова.
        path: абсолютный путь файла с раскрытыми ссылками.

    Возвращает: Текст отказа, если файл в черновике не раздел ответа; None для разделов и для путей вне черновика.
    """
    draft_dir = workspace.draft_dir.resolve()
    if not path.is_relative_to(draft_dir):
        return None

    shown_draft_dir = workspace.display_path(path = draft_dir)
    if path.name == workspace.context_file.name:
        return CONTEXT_IN_DRAFT_REFUSAL.format(
            context_name = workspace.context_file.name,
            draft_dir = shown_draft_dir,
            context_file = workspace.display_path(path = workspace.context_file.resolve()),
        )

    relative_path = path.relative_to(draft_dir)
    if len(relative_path.parts) != 1 or not DRAFT_SECTION_PATTERN.match(path.name):
        return NOT_DRAFT_SECTION_REFUSAL.format(name = relative_path.as_posix(), draft_dir = shown_draft_dir)

    return None
