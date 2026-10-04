"""Файлы, которые видел вызов: write и edit меняют существующий файл, только если вызов его видел
и файл с тех пор не менялся."""

import hashlib
from pathlib import Path


class SeenFiles:
    """
    Хранит отпечатки содержимого файлов, которое видел вызов; общие для read, write и edit одного вызова.
    """

    def __init__(self) -> None:
        self._hashes: dict[Path, str] = {}

    def remember(self, *, path: Path, content: bytes) -> None:
        """
        Запоминает содержимое файла как виденное вызовом.

            path: абсолютный путь файла.
            content: байты файла.
        """
        self._hashes[path] = _hash(content = content)

    def forget_all(self) -> None:
        """
        Забывает все виденные файлы.
        """
        self._hashes.clear()

    def stale_reason(self, *, path: Path, shown_path: str) -> str | None:
        """
        Проверяет, можно ли менять существующий файл.

            path: абсолютный путь файла.
            shown_path: путь файла для текста ошибки.

        Возвращает: Текст ошибки, если файл не читан или изменился после чтения, иначе None.
        """
        seen_hash = self._hashes.get(path)
        if seen_hash is None:
            return f"Ошибка: файл {shown_path} не прочитан. Прочитай его инструментом read и повтори."

        if seen_hash != _hash(content = path.read_bytes()):
            return (
                f"Ошибка: файл {shown_path} изменился после твоего чтения. "
                "Прочитай его заново инструментом read и повтори."
            )

        return None


def _hash(*, content: bytes) -> str:
    """
    Считает отпечаток содержимого.

        content: содержимое файла.

    Возвращает: Отпечаток sha256 шестнадцатеричной строкой.
    """
    return hashlib.sha256(content).hexdigest()
