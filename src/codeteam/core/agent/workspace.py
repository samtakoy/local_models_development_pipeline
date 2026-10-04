"""Рабочее место вызова агента: папки, доступные для чтения и записи, и закрытые имена."""

from dataclasses import dataclass
from pathlib import Path

# Папка личных папок запусков внутри проекта.
PRIVATE_ROOT = Path(".ct-work")

# Имена файлов, закрытых для агента на любой глубине проекта.
CLOSED_FILE_NAMES = (".env",)

# Файлы и папки, закрытые для файловых инструментов агента, в виде правил .gitignore:
# закрытые файлы на любой глубине и всё содержимое папки личных папок; своя личная папка
# открывается отдельно.
CLOSED_NAMES = (
    *CLOSED_FILE_NAMES,
    f"/{PRIVATE_ROOT.as_posix()}/*",
)


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
