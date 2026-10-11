"""Рабочее место вызова агента: папки, доступные для чтения и записи, и закрытые имена."""

import re
from dataclasses import dataclass
from pathlib import Path

# Папка личных папок запусков внутри проекта.
PRIVATE_ROOT = Path(".ct-work")

# Папка временных скриптов и данных проверки в корне проекта.
CHECK_DIR = Path("tmp_check")

# Папка черновика и файл контекста внутри личной папки.
DRAFT_DIR_NAME = "draft"
CONTEXT_FILE_NAME = "context.md"

# Окончание имени папки помощников агента: рядом с личной папкой, <личная папка>_help.
HELPERS_DIR_SUFFIX = "_help"

# Имя раздела черновика: номер, тема буквами любого алфавита, .md. Группа 1 — номер раздела.
DRAFT_SECTION_PATTERN = re.compile(r"^(\d+)_[\w-]+\.md$")

# Рекомендуемое имя раздела черновика: номер, тема латиницей, .md.
LATIN_DRAFT_SECTION_PATTERN = re.compile(r"^(\d+)_[A-Za-z0-9_-]+\.md$")

# Имена файлов, закрытых для агента на любой глубине проекта.
CLOSED_FILE_NAMES = (".env",)

# Файлы и папки, закрытые для файловых инструментов агента, в виде правил .gitignore:
# закрытые файлы на любой глубине и всё содержимое папки личных папок; своя личная папка
# открывается отдельно.
CLOSED_NAMES = (
    *CLOSED_FILE_NAMES,
    f"/{PRIVATE_ROOT.as_posix()}/*",
)


def draft_dir(*, private_dir: Path) -> Path:
    """
    Строит путь папки черновика.

        private_dir: личная папка агента.

    Возвращает: Папку черновика внутри личной папки.
    """
    return private_dir / DRAFT_DIR_NAME


def context_path(*, private_dir: Path) -> Path:
    """
    Строит путь файла контекста.

        private_dir: личная папка агента.

    Возвращает: Файл контекста внутри личной папки, рядом с черновиком.
    """
    return private_dir / CONTEXT_FILE_NAME


def helpers_dir(*, private_dir: Path) -> Path:
    """
    Строит путь папки помощников агента: в ней личные папки агентов, которых он вызывает инструментами.

        private_dir: личная папка агента.

    Возвращает: Папку рядом с личной папкой: <личная папка>_help.
    """
    return private_dir.with_name(f"{private_dir.name}{HELPERS_DIR_SUFFIX}")


class PathOutsideWorkspace(ValueError):
    """Путь лежит вне папок, доступных вызову."""


@dataclass(frozen = True)
class Workspace:
    """
    Рабочее место одного вызова агента.

        project_dir: общая папка проекта; относительные пути считаются от неё.
        private_dir: личная папка вызова: черновик, журнал, ответ.
        input_dirs: папки результатов других агентов; открыты для чтения внутри закрытой папки
            личных папок.
        readable_dirs: папки, где вызову разрешено чтение.
        writable_dirs: папки, где вызову разрешены запись и правка.
        refusal_hint: пояснение к отказу по пути для агента, None — без пояснения.
    """

    project_dir: Path
    private_dir: Path
    input_dirs: tuple[Path, ...]
    readable_dirs: tuple[Path, ...]
    writable_dirs: tuple[Path, ...]
    refusal_hint: str | None

    @property
    def draft_dir(self) -> Path:
        """Папка черновика вызова: разделы ответа."""
        return draft_dir(private_dir = self.private_dir)

    @property
    def context_file(self) -> Path:
        """Файл контекста вызова для следующего агента той же роли."""
        return context_path(private_dir = self.private_dir)

    @property
    def helpers_dir(self) -> Path:
        """Папка помощников вызова: личные папки агентов, которых он вызывает инструментами."""
        return helpers_dir(private_dir = self.private_dir)

    def resolve_readable(self, *, path: str) -> Path:
        """
        Переводит путь от агента в абсолютный и проверяет право чтения.

            path: путь от агента, абсолютный или относительно папки проекта.

        Возвращает: Абсолютный путь внутри папок чтения.
        """
        resolved = self._resolve(path = path)
        if not _is_inside_any(path = resolved, roots = self.readable_dirs):
            shown = self.show_folders(folders = self.readable_dirs)
            raise PathOutsideWorkspace(
                self._with_hint(message = f"путь {path} вне доступных папок: {shown}")
            )

        return resolved

    def resolve_writable(self, *, path: str) -> Path:
        """
        Переводит путь от агента в абсолютный и проверяет право записи.

            path: путь от агента, абсолютный или относительно папки проекта.

        Возвращает: Абсолютный путь внутри папок записи.
        """
        resolved = self._resolve(path = path)
        if not _is_inside_any(path = resolved, roots = self.writable_dirs):
            shown = self.show_folders(folders = self.writable_dirs)
            raise PathOutsideWorkspace(
                self._with_hint(message = f"запись в {path} запрещена, разрешены папки: {shown}")
            )

        return resolved

    def display_path(self, *, path: Path) -> str:
        """
        Показывает путь агенту: относительно папки проекта, если он внутри неё.

            path: абсолютный путь.

        Возвращает: Путь для текста ответа инструмента.
        """
        if path.is_relative_to(self.project_dir.resolve()):
            return str(path.relative_to(self.project_dir.resolve()))

        return str(path)

    def show_folders(self, *, folders: tuple[Path, ...]) -> str:
        """
        Перечисляет папки для текста ошибки так же, как агент видит пути: относительно проекта.

            folders: папки.

        Возвращает: Папки через запятую; сама папка проекта называется словами.
        """
        shown = [self.display_path(path = folder.resolve()) for folder in folders]

        return ", ".join("папка проекта" if folder == "." else folder for folder in shown)

    def _resolve(self, *, path: str) -> Path:
        """
        Переводит путь от агента в абсолютный с раскрытием ссылок и `..`.

            path: путь от агента.

        Возвращает: Абсолютный путь.
        """
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_dir / candidate

        return candidate.resolve()

    def _with_hint(self, *, message: str) -> str:
        """
        Добавляет к тексту отказа пояснение рабочего места.

            message: текст отказа.

        Возвращает: Текст отказа с пояснением или без него.
        """
        if self.refusal_hint is None:
            return message

        return f"{message}. {self.refusal_hint}"


def _is_inside_any(*, path: Path, roots: tuple[Path, ...]) -> bool:
    """
    Проверяет, лежит ли путь внутри одной из папок.

        path: абсолютный путь.
        roots: папки.

    Возвращает: True, если путь внутри хотя бы одной папки.
    """
    return any(path.is_relative_to(root.resolve()) for root in roots)
