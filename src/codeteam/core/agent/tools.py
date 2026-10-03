from pathlib import Path

from langchain_core.tools import tool


@tool
def read_file(path: str) -> str:
    """Читает текстовый файл или показывает содержимое папки. path: абсолютный путь."""
    target = Path(path)
    if target.is_dir():
        return "\n".join(sorted(entry.name for entry in target.iterdir()))

    return target.read_text(encoding = "utf-8")