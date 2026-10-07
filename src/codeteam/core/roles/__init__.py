"""Промпты ролей агентов: один файл <имя роли>.md на роль."""

from pathlib import Path

# Папка файлов промптов ролей.
ROLES_DIR = Path(__file__).parent


def load_role_prompt(*, name: str, fields: dict[str, str]) -> str:
    """
    Читает промпт роли и подставляет в него поля.

        name: имя роли.
        fields: значения полей вида {имя поля} в тексте промпта.

    Возвращает: Текст промпта роли.
    """
    return (ROLES_DIR / f"{name}.md").read_text(encoding = "utf-8").strip().format(**fields)
