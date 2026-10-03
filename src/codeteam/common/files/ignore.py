"""Правила пропуска файлов проекта: список скрытых имён и .gitignore из корня проекта.

Правила скрывают файлы от поиска и показа папок и закрывают их для чтения файловыми инструментами.
Команды bash правила не учитывают: скрытый файл, например .env, читается командой cat.
"""

import os
from collections.abc import Iterator
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
        names: правила по списку скрытых имён.
        gitignore: правила из .gitignore корня проекта.
    """

    project_dir: Path
    open_dirs: tuple[Path, ...]
    names: GitIgnoreSpec
    gitignore: GitIgnoreSpec

    def is_ignored(self, *, path: Path) -> bool:
        """
        Проверяет, скрыт ли файл или папка правилами.

            path: абсолютный путь с раскрытыми ссылками.

        Возвращает: True для путей внутри проекта, подпавших под правила. Сама папка проекта,
            пути вне проекта и пути в открытых папках не скрываются.
        """
        if path == self.project_dir or not path.is_relative_to(self.project_dir):
            return False

        if any(path.is_relative_to(folder) for folder in self.open_dirs):
            return False

        relative_path = path.relative_to(self.project_dir).as_posix()
        if path.is_dir():
            relative_path += "/"

        return self.names.match_file(relative_path) or self.gitignore.match_file(relative_path)


def load_ignore_rules(
    *,
    project_dir: Path,
    ignored_names: tuple[str, ...],
    open_dirs: tuple[Path, ...],
) -> IgnoreRules:
    """
    Собирает правила пропуска проекта из списка скрытых имён и .gitignore в корне проекта.

    Вложенные .gitignore в подпапках не учитываются: требует доработки.

        project_dir: папка проекта.
        ignored_names: имена файлов и папок, скрытые на любой глубине; запись в виде правил .gitignore.
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
        names = GitIgnoreSpec.from_lines(ignored_names),
        gitignore = GitIgnoreSpec.from_lines(gitignore_lines),
    )


def visible_files(*, rules: IgnoreRules, root: Path) -> Iterator[Path]:
    """
    Обходит папку и выдаёт файлы, не скрытые правилами. Ссылки на файлы и папки пропускает.

        rules: правила пропуска.
        root: папка обхода, абсолютный путь с раскрытыми ссылками.

    Возвращает: Абсолютные пути файлов: сначала файлы папки по алфавиту, затем подпапки по алфавиту.
    """
    for folder, folder_names, file_names in os.walk(root):
        folder_path = Path(folder)
        folder_names[:] = sorted(
            name for name in folder_names
            if not (folder_path / name).is_symlink() and not rules.is_ignored(path = folder_path / name)
        )
        for name in sorted(file_names):
            file_path = folder_path / name
            if not file_path.is_symlink() and not rules.is_ignored(path = file_path):
                yield file_path
