"""Промпты ролей агентов: один файл <имя роли>.md на роль."""

from pathlib import Path

# Папка файлов промптов ролей.
ROLES_DIR = Path(__file__).parent


def load_role_prompt(*, name: str) -> str:
    """
    Читает промпт роли.

        name: имя роли.

    Возвращает: Текст промпта роли.
    """
    return (ROLES_DIR / f"{name}.md").read_text(encoding = "utf-8").strip()
