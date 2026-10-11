"""Хуки после шага инструментов: проверяют изменённые на шаге файлы личной папки агента и дают агенту замечания."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codeteam.core.agent.prompts import CODE_BLOCK_LINES, DUPLICATE_SECTION_NUMBER_REMARK, \
    LATIN_SECTION_NAME_REMARK, MISPLACED_ANSWER_FILE_REMARK, MISPLACED_CONTEXT_FILE_REMARK, MISPLACED_CONTEXT_REMARK, \
    NOT_DRAFT_SECTION_REMARK, ONLY_ANSWER_FILES_REMARK, STRAY_PRIVATE_FILE_REMARK
from codeteam.core.agent.workspace import CONTEXT_FILE_NAME, DRAFT_SECTION_PATTERN, LATIN_DRAFT_SECTION_PATTERN, \
    context_path, draft_dir

# Хук после шага: путь и текст изменённого файла → замечание агенту или None.
StepHook = Callable[[Path, str], str | None]

# Проверка после шага: смотрит не на черновик, а на что угодно ещё (например, на проект) → замечание агенту или None.
StepCheck = Callable[[], str | None]


@dataclass(frozen = True)
class _CodeBlock:
    """
    Блок с указанным языком в тексте файла.

        first_line: номер строки открывающей ограды, с 1.
        last_line: номер строки закрывающей ограды; у незакрытого блока - последняя строка файла.
        line_count: число строк внутри блока.
    """

    first_line: int
    last_line: int
    line_count: int


@dataclass(frozen = True)
class FolderHook:
    """
    Хук после шага и папка, за которой он следит.

        folder: папка относительно личной папки агента, подпапки входят; Path(".") — вся личная папка.
        hook: хук: получает каждый изменённый за шаг файл из папки.
    """

    folder: Path
    hook: StepHook


# Строка, открывающая блок с указанным языком: ``` и имя языка.
LANGUAGE_BLOCK_START_PATTERN = re.compile(r"^```[A-Za-z0-9_+#.-]+$")

# Граница блока: строка, начинающаяся с ```.
BLOCK_FENCE = "```"

# Имя, похожее на файл контекста: номер раздела и имя файла контекста.
CONTEXT_LIKE_NAME_PATTERN = re.compile(rf"^\d+_{re.escape(CONTEXT_FILE_NAME)}$")


def private_file_hook(
    *,
    project_dir: Path,
    private_dir: Path,
    answer_file_names: tuple[str, ...],
    only_answer_files: bool,
) -> StepHook:
    """
    Собирает хук личной папки: проверяет место и имя изменённого файла. Правила по порядку, срабатывает первое:
    1. файл контекста на своём месте — замечания нет;
    2. файл контекста лежит в другом месте личной папки — путь файла контекста;
    3. имя похоже на файл контекста: номер и имя файла контекста — путь файла контекста;
    4. файл ответа роли лежит не в черновике под своим именем — его путь в черновике;
    5. в черновике роли, где разрешены только файлы ответа, другой файл — пути файлов ответа;
    6. файл в черновике — проверки имени раздела;
    7. остальные файлы — общее замечание о местах файлов личной папки.

        project_dir: папка проекта: пути в замечаниях показываются от неё.
        private_dir: личная папка агента.
        answer_file_names: заранее известные имена файлов ответа роли в черновике.
        only_answer_files: в черновике роли разрешены только файлы ответа.

    Возвращает: Хук после шага для папки Path(".").
    """
    agent_draft_dir = draft_dir(private_dir = private_dir)
    agent_context_file = context_path(private_dir = private_dir)

    def shown(*, path: Path) -> str:
        """Показывает путь агенту от папки проекта."""
        return path.relative_to(project_dir).as_posix()

    def hook(path: Path, text: str) -> str | None:
        """Находит файл не на своём месте или с неверным именем и даёт замечание с правильным путём."""
        if path == agent_context_file:
            return None

        # context.md не на своем месте
        if path.name == agent_context_file.name:
            return MISPLACED_CONTEXT_FILE_REMARK.format(
                file_path = shown(path = path),
                context_path = shown(path = agent_context_file),
            )

        # файл похожий на context.md не на своем месте
        if CONTEXT_LIKE_NAME_PATTERN.match(path.name):
            return MISPLACED_CONTEXT_REMARK.format(
                file_path = shown(path = path),
                context_path = shown(path = agent_context_file),
            )

        # имя черновика требуемое ответом не на своем месте
        answer_path = agent_draft_dir / path.name
        if path.name in answer_file_names and path != answer_path:
            return MISPLACED_ANSWER_FILE_REMARK.format(
                file_path = shown(path = path),
                answer_path = shown(path = answer_path),
            )

        # в черновики упал файл, но там было ограничение на разрешенные имена
        is_draft_file = path.is_relative_to(agent_draft_dir)
        if is_draft_file and only_answer_files and path.name not in answer_file_names:
            return ONLY_ANSWER_FILES_REMARK.format(
                file_path = shown(path = path),
                answer_paths = ", ".join(shown(path = agent_draft_dir / name) for name in answer_file_names),
            )

        # отдельные проверки на нейминг файлов черновика
        if is_draft_file:
            return _draft_section_remark(path = path)

        return STRAY_PRIVATE_FILE_REMARK.format(
            file_path = shown(path = path),
            private_dir = shown(path = private_dir),
            draft_dir = shown(path = agent_draft_dir),
            context_path = shown(path = agent_context_file),
        )

    return hook


def _draft_section_remark(*, path: Path) -> str | None:
    """
    Проверяет имя изменённого файла черновика: раздел ли это, латиница ли в теме, нет ли рядом
    разделов с тем же номером.

        path: путь изменённого файла черновика.

    Возвращает: Замечания агенту одной строкой или None, если имя раздела в порядке.
    """
    section_match = DRAFT_SECTION_PATTERN.match(path.name)
    if section_match is None:
        return NOT_DRAFT_SECTION_REMARK.format(file_name = path.name)

    remarks = []
    if not LATIN_DRAFT_SECTION_PATTERN.match(path.name):
        remarks.append(LATIN_SECTION_NAME_REMARK.format(file_name = path.name))

    same_number_names = _same_number_section_names(path = path, number = section_match.group(1))
    if same_number_names:
        remarks.append(
            DUPLICATE_SECTION_NUMBER_REMARK.format(file_name = path.name, other_names = ", ".join(same_number_names))
        )

    return "\n".join(remarks) if remarks else None


def code_block_hook(*, max_lines: int, remark: str, skip_file_names: tuple[str, ...]) -> StepHook:
    """
    Собирает хук, который замечает в файле черновика блоки с указанным языком длиннее предела.

        max_lines: наибольшее число строк внутри одного блока с указанным языком.
        remark: текст замечания агенту; поля {file_name}, {max_lines} и {long_blocks} в нём заменяются
            именем файла, пределом и строками всех блоков длиннее предела.
        skip_file_names: имена файлов черновика, которые хук не проверяет.

    Возвращает: Хук после шага.
    """
    def hook(path: Path, text: str) -> str | None:
        """Находит блоки с указанным языком длиннее предела и называет их строки."""
        if path.name in skip_file_names:
            return None

        long_blocks = [block for block in _language_blocks(text = text) if block.line_count > max_lines]
        if not long_blocks:
            return None

        shown_blocks = "; ".join(
            CODE_BLOCK_LINES.format(first_line = block.first_line, last_line = block.last_line)
            for block in long_blocks
        )

        return remark.format(file_name = path.name, max_lines = max_lines, long_blocks = shown_blocks)

    return hook


def _same_number_section_names(*, path: Path, number: str) -> list[str]:
    """
    Находит в папке раздела другие разделы с тем же номером.

        path: путь раздела черновика.
        number: номер раздела, как он записан в имени.

    Возвращает: Имена других разделов с тем же номером по порядку имён.
    """
    names = []
    for sibling in sorted(path.parent.glob("*.md")):
        sibling_match = DRAFT_SECTION_PATTERN.match(sibling.name)
        if sibling != path and sibling_match is not None and sibling_match.group(1) == number:
            names.append(sibling.name)

    return names


def _language_blocks(*, text: str) -> list[_CodeBlock]:
    """
    Находит блоки с указанным языком; блоки без языка пропускает.

        text: текст файла.

    Возвращает: Блоки с указанным языком по порядку.
    """
    blocks = []
    inside_block = False
    is_language_block = False
    first_line = 0
    line_count = 0
    lines = text.splitlines()
    for number, line in enumerate(lines, start = 1):
        stripped_line = line.strip()
        if not inside_block:
            if stripped_line.startswith(BLOCK_FENCE):
                inside_block = True
                is_language_block = LANGUAGE_BLOCK_START_PATTERN.match(stripped_line) is not None
                first_line = number
                line_count = 0
            continue

        if stripped_line == BLOCK_FENCE:
            if is_language_block:
                blocks.append(_CodeBlock(first_line = first_line, last_line = number, line_count = line_count))
            inside_block = False
            continue

        line_count += 1

    if inside_block and is_language_block:
        blocks.append(_CodeBlock(first_line = first_line, last_line = len(lines), line_count = line_count))

    return blocks
