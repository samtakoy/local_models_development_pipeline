"""Правила пропуска файлов проекта: закрытые имена и пропуск при поиске.

Закрытые файлы и папки файловые инструменты не показывают, не ищут, не читают и не записывают.
Пропускаемые при поиске видны в списке папки и доступны по пути, но обход папок при поиске в них не заходит.
Команды bash правила не учитывают: закрытый файл, например .env, читается командой cat.
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

# Файл правил git в корне проекта.
GITIGNORE_FILE_NAME = ".gitignore"


@dataclass(frozen = True)
class IgnoreRules:
    """
    Правила пропуска файлов одного проекта. Пути — абсолютные, с раскрытыми ссылками.

        project_dir: папка проекта; правила сверяются с путями относительно неё.
        open_dirs: папки внутри проекта, к которым правила не применяются.
        closed: правила закрытых файлов и папок.
        search_skipped: правила файлов и папок, пропускаемых при поиске: служебные имена и .gitignore.
    """

    project_dir: Path
    open_dirs: tuple[Path, ...]
    closed: GitIgnoreSpec
    search_skipped: GitIgnoreSpec

    def is_closed(self, *, path: Path) -> bool:
        """
        Проверяет, закрыт ли файл или папка.

            path: абсолютный путь с раскрытыми ссылками.

        Возвращает: True для путей внутри проекта, подпавших под закрытые правила. Сама папка проекта,
            пути вне проекта и пути в открытых папках не закрываются.
        """
        relative_path = self._checked_path(path = path)
        if relative_path is None:
            return False

        return self.closed.match_file(relative_path)

    def is_skipped_in_search(self, *, path: Path) -> bool:
        """
        Проверяет, пропускается ли файл или папка при поиске.

            path: абсолютный путь с раскрытыми ссылками.

        Возвращает: True для закрытых путей и путей, подпавших под правила пропуска при поиске.
        """
        relative_path = self._checked_path(path = path)
        if relative_path is None:
            return False

        return self.closed.match_file(relative_path) or self.search_skipped.match_file(relative_path)

    def _checked_path(self, *, path: Path) -> str | None:
        """
        Переводит путь в вид для сверки с правилами.

            path: абсолютный путь с раскрытыми ссылками.

        Возвращает: Путь относительно папки проекта, у папки — с косой чертой в конце; None для самой
            папки проекта, путей вне проекта и путей в открытых папках.
        """
        if path == self.project_dir or not path.is_relative_to(self.project_dir):
            return None

        if any(path.is_relative_to(folder) for folder in self.open_dirs):
            return None

        relative_path = path.relative_to(self.project_dir).as_posix()
        if path.is_dir():
            relative_path += "/"

        return relative_path


def load_ignore_rules(
    *,
    project_dir: Path,
    closed_names: tuple[str, ...],
    search_skipped_names: tuple[str, ...],
    open_dirs: tuple[Path, ...],
) -> IgnoreRules:
    """
    Собирает правила пропуска проекта: закрытые имена, а для поиска — служебные имена и .gitignore
    в корне проекта.

    Вложенные .gitignore в подпапках не учитываются: требует доработки.

        project_dir: папка проекта.
        closed_names: имена закрытых файлов и папок на любой глубине; запись в виде правил .gitignore.
        search_skipped_names: имена файлов и папок, пропускаемых при поиске; запись в виде правил .gitignore.
        open_dirs: папки внутри проекта, к которым правила не применяются.

    Возвращает: Правила пропуска.
    """
    gitignore_path = project_dir / GITIGNORE_FILE_NAME
    gitignore_lines = []
    if gitignore_path.is_file():
        gitignore_lines = gitignore_path.read_text(encoding = "utf-8", errors = "replace").splitlines()

    return IgnoreRules(
        project_dir = project_dir.resolve(),
        open_dirs = tuple(folder.resolve() for folder in open_dirs),
        closed = GitIgnoreSpec.from_lines(closed_names),
        search_skipped = GitIgnoreSpec.from_lines([*search_skipped_names, *gitignore_lines]),
    )


def visible_files(*, rules: IgnoreRules, root: Path) -> Iterator[Path]:
    """
    Обходит папку для поиска и выдаёт файлы, не пропускаемые правилами. Ссылки на файлы и папки пропускает.

    Если сама папка обхода пропускается при поиске, внутри неё пропускаются только закрытые файлы и папки.

        rules: правила пропуска.
        root: папка обхода, абсолютный путь с раскрытыми ссылками.

    Возвращает: Абсолютные пути файлов: сначала файлы папки по алфавиту, затем подпапки по алфавиту.
    """
    is_skipped: Callable[..., bool] = rules.is_skipped_in_search
    if rules.is_skipped_in_search(path = root):
        is_skipped = rules.is_closed

    for folder, folder_names, file_names in os.walk(root):
        folder_path = Path(folder)
        folder_names[:] = sorted(
            name for name in folder_names
            if not (folder_path / name).is_symlink() and not is_skipped(path = folder_path / name)
        )
        for name in sorted(file_names):
            file_path = folder_path / name
            if not file_path.is_symlink() and not is_skipped(path = file_path):
                yield file_path
