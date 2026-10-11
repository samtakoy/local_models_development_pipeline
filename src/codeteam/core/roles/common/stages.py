"""Этапы плана архитектора: файлы этапов, папки этапов."""

from pathlib import Path

from codeteam.core.agent.workspace import DRAFT_SECTION_PATTERN

# Файл этапа в черновике архитектора — раздел черновика: номер этапа, тема, .md.
STAGE_FILE_PATTERN = DRAFT_SECTION_PATTERN

# Папка внутри личной папки этапа: копии общего решения и файла этапа, вход сеньора и приёмщика этапа.
STAGE_TASK_DIR_NAME = "task"


def build_stage_dir_name(*, stage_file: Path) -> Path:
    """
    Строит имя личной папки этапа по файлу этапа.

        stage_file: файл этапа.

    Возвращает: Путь папки этапа внутри папки личных папок: s<номер этапа>.
    """
    return Path(f"stage_{parse_stage_number(stage_file = stage_file)}")


def parse_stage_number(*, stage_file: Path) -> str:
    """
    Берёт номер этапа из имени файла этапа.

        stage_file: файл этапа.

    Возвращает: Номер этапа, как он записан в имени файла, например 100.
    """
    return STAGE_FILE_PATTERN.match(stage_file.name).group(1)


def read_stage_title(*, stage_file: Path) -> str:
    """
    Берёт заголовок этапа: первую непустую строку файла этапа без знаков заголовка markdown.

        stage_file: файл этапа.

    Возвращает: Заголовок этапа; имя файла, если файл пустой.
    """
    for line in stage_file.read_text(encoding = "utf-8").splitlines():
        title = line.strip().lstrip("#").strip()
        if title:
            return title

    return stage_file.name
