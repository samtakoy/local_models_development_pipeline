"""Файлы ответа роли в черновике и правила черновика ответа для общих инструкций агента."""

from dataclasses import dataclass

from codeteam.core.agent.prompts import DRAFT_SECTION_RULES, ONLY_ANSWER_FILES_RULES, REQUIRED_ANSWER_FILES_RULE


@dataclass(frozen = True)
class AnswerFiles:
    """
    Файлы ответа роли в черновике.

        names: заранее известные имена файлов ответа.
        only_these: в черновике разрешены только эти файлы.
    """

    names: tuple[str, ...]
    only_these: bool

    def __post_init__(self) -> None:
        """Проверяет, что у роли с одними файлами ответа их имена заданы."""
        if self.only_these and not self.names:
            raise ValueError("only_these задан без имён файлов ответа")


def build_draft_rules(*, answer_files: AnswerFiles, shown_draft_dir: str) -> str:
    """
    Собирает правила черновика ответа роли для общих инструкций агента.

        answer_files: файлы ответа роли в черновике.
        shown_draft_dir: папка черновика от папки проекта.

    Возвращает:
        Строки правил: только файлы ответа — для роли с одними файлами ответа; правила разделов и строка
        обязательных файлов — для роли с заранее известными файлами; правила разделов — для остальных.
    """
    file_names = ", ".join(answer_files.names)
    if answer_files.only_these:
        return ONLY_ANSWER_FILES_RULES.format(file_names = file_names, draft_dir = shown_draft_dir)

    section_rules = DRAFT_SECTION_RULES.format(draft_dir = shown_draft_dir)
    if not answer_files.names:
        return section_rules

    return section_rules + "\n" + REQUIRED_ANSWER_FILES_RULE.format(file_names = file_names)
