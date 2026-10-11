"""Хуки шага инструментов: после всех вызовов шага смотрят на изменённые файлы личной папки агента, на отказы
по пути или на проект и дают агенту замечания."""

import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codeteam.core.agent.prompts import ANSWER_LIKE_FILE_REMARK, CODE_BLOCK_LINES, DRAFT_PHASE_HINT, \
    DUPLICATE_SECTION_NUMBER_REMARK, LATIN_SECTION_NAME_REMARK, MISPLACED_ANSWER_FILE_REMARK, \
    MISPLACED_CONTEXT_FILE_REMARK, MISPLACED_CONTEXT_REMARK, NOT_DRAFT_SECTION_REMARK, ONLY_ANSWER_FILES_REMARK, \
    STRAY_PRIVATE_FILE_REMARK
from codeteam.core.agent.statistics import DRAFT_PHASE
from codeteam.core.agent.workspace import CONTEXT_FILE_NAME, DRAFT_SECTION_PATTERN, LATIN_DRAFT_SECTION_PATTERN, \
    context_path, draft_dir
from codeteam.core.tools.files import PathRefusal


@dataclass(frozen = True)
class StepContext:
    """
    Шаг инструментов: что нужно хукам шага.

        project_dir: папка проекта.
        private_dir: личная папка агента.
        phase: фаза работы агента, в которой сделан шаг.
        changed_files: файлы личной папки, которые появились или изменились за шаг, по порядку путей.
        refusals: отказы файловых инструментов по пути за шаг.
    """

    project_dir: Path
    private_dir: Path
    phase: str
    changed_files: tuple[Path, ...]
    refusals: tuple[PathRefusal, ...]


# Хук шага: шаг инструментов → замечание агенту или None.
StepHook = Callable[[StepContext], str | None]


@dataclass(frozen = True)
class ChangedFile:
    """
    Изменённый за шаг файл с текстом.

        path: путь файла.
        text: текст файла.
    """

    path: Path
    text: str


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


# Строка, открывающая блок с указанным языком: ``` и имя языка.
LANGUAGE_BLOCK_START_PATTERN = re.compile(r"^```[A-Za-z0-9_+#.-]+$")

# Граница блока: строка, начинающаяся с ```.
BLOCK_FENCE = "```"

# Имя, похожее на файл контекста: номер раздела и имя файла контекста.
CONTEXT_LIKE_NAME_PATTERN = re.compile(rf"^\d+_{re.escape(CONTEXT_FILE_NAME)}$")


def read_changed_files(*, context: StepContext, folder: Path) -> list[ChangedFile]:
    """
    Читает изменённые за шаг файлы из папки внутри личной папки.

        context: шаг инструментов.
        folder: папка относительно личной папки, подпапки входят; Path(".") — вся личная папка.

    Возвращает: Изменённые файлы папки с текстом по порядку путей.
    """
    root = context.private_dir / folder

    return [
        ChangedFile(path = path, text = path.read_text(encoding = "utf-8", errors = "replace"))
        for path in context.changed_files
        if path.is_relative_to(root)
    ]


def join_remarks(*, remarks: list[str]) -> str | None:
    """
    Склеивает замечания хука по файлам в одно.

        remarks: замечания по порядку файлов.

    Возвращает: Замечания через пустую строку; None, если замечаний нет.
    """
    return "\n\n".join(remarks) if remarks else None


def refusal_hint_hook(*, phase: str, hints: tuple[str, ...]) -> StepHook:
    """
    Собирает хук шага: если в шаге фазы phase был отказ файлового инструмента по пути — одна подсказка из набора.

        phase: фаза работы агента, в которой хук даёт подсказку.
        hints: подсказки агенту.

    Возвращает: Хук шага.
    """

    def hook(context: StepContext) -> str | None:
        """Даёт подсказку к отказам по пути за шаг."""
        if context.phase != phase or not context.refusals:
            return None

        return random.choice(hints)

    return hook


def draft_phase_hint_hook(context: StepContext) -> str | None:
    """
    Хук шага: в шаге фазы черновика был отказ файлового инструмента по пути — подсказка о том, что сейчас
    разрешено.

        context: шаг инструментов.

    Возвращает: Подсказку или None.
    """
    if context.phase != DRAFT_PHASE or not context.refusals:
        return None

    return DRAFT_PHASE_HINT.format(
        private_dir = context.private_dir.relative_to(context.project_dir).as_posix(),
        context_file_path = CONTEXT_FILE_NAME,
    )


def private_file_hook(*, answer_file_names: tuple[str, ...], only_answer_files: bool) -> StepHook:
    """
    Собирает хук личной папки: проверяет место и имя каждого изменённого файла. Правила по порядку,
    срабатывает первое:
    1. файл контекста на своём месте — замечания нет;
    2. файл контекста лежит в другом месте личной папки — путь файла контекста;
    3. имя похоже на файл контекста: номер и имя файла контекста — путь файла контекста;
    4. файл ответа роли лежит не в черновике под своим именем — его путь в черновике;
       то же для раздела с темой файла ответа под другим номером, например 100_verdict.md для 000_verdict.md;
    5. в черновике роли, где разрешены только файлы ответа, другой файл — пути файлов ответа;
    6. файл в черновике — проверки имени раздела;
    7. остальные файлы — общее замечание о местах файлов личной папки.

        answer_file_names: заранее известные имена файлов ответа роли в черновике.
        only_answer_files: в черновике роли разрешены только файлы ответа.

    Возвращает: Хук шага: замечания к изменённым файлам всей личной папки.
    """

    def hook(context: StepContext) -> str | None:
        """Находит файлы не на своём месте или с неверным именем и даёт замечания с правильными путями."""
        remarks = [
            remark
            for path in context.changed_files
            if (remark := _private_file_remark(
                context = context,
                path = path,
                answer_file_names = answer_file_names,
                only_answer_files = only_answer_files,
            )) is not None
        ]

        return join_remarks(remarks = remarks)

    return hook


def _private_file_remark(
    *,
    context: StepContext,
    path: Path,
    answer_file_names: tuple[str, ...],
    only_answer_files: bool,
) -> str | None:
    """
    Проверяет место и имя одного изменённого файла личной папки по правилам private_file_hook.

        context: шаг инструментов: папка проекта, от которой показываются пути, и личная папка.
        path: путь изменённого файла.
        answer_file_names: заранее известные имена файлов ответа роли в черновике.
        only_answer_files: в черновике роли разрешены только файлы ответа.

    Возвращает: Замечание с правильным путём или None, если файл на своём месте.
    """
    agent_draft_dir = draft_dir(private_dir = context.private_dir)
    agent_context_file = context_path(private_dir = context.private_dir)
    # файл ответа роли по теме его имени
    answer_names_by_topic = {_section_topic(name = name): name for name in answer_file_names}

    def shown(*, path: Path) -> str:
        """Показывает путь агенту от папки проекта."""
        return path.relative_to(context.project_dir).as_posix()

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

    # раздел с темой файла ответа под другим номером
    answer_name = answer_names_by_topic.get(_section_topic(name = path.name))
    if answer_name is not None and path.name != answer_name:
        return ANSWER_LIKE_FILE_REMARK.format(
            file_path = shown(path = path),
            answer_name = answer_name,
            answer_path = shown(path = agent_draft_dir / answer_name),
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
        private_dir = shown(path = context.private_dir),
        draft_dir = shown(path = agent_draft_dir),
        context_path = shown(path = agent_context_file),
    )


def _section_topic(*, name: str) -> str | None:
    """
    Находит тему в имени раздела черновика: часть имени после номера.

        name: имя файла.

    Возвращает: Тему с расширением, например verdict.md для 000_verdict.md; None, если имя не раздел черновика.
    """
    if DRAFT_SECTION_PATTERN.match(name) is None:
        return None

    return name.split("_", 1)[1]


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


def code_block_hook(*, folder: Path, max_lines: int, remark: str, skip_file_names: tuple[str, ...]) -> StepHook:
    """
    Собирает хук, который замечает в изменённых файлах папки блоки с указанным языком длиннее предела.

        folder: папка относительно личной папки, подпапки входят.
        max_lines: наибольшее число строк внутри одного блока с указанным языком.
        remark: текст замечания агенту; поля {file_name}, {max_lines} и {long_blocks} в нём заменяются
            именем файла, пределом и строками всех блоков длиннее предела.
        skip_file_names: имена файлов, которые хук не проверяет.

    Возвращает: Хук шага.
    """
    def file_remark(changed_file: ChangedFile) -> str | None:
        """Находит в файле блоки с указанным языком длиннее предела и называет их строки."""
        if changed_file.path.name in skip_file_names:
            return None

        long_blocks = [block for block in _language_blocks(text = changed_file.text) if block.line_count > max_lines]
        if not long_blocks:
            return None

        shown_blocks = "; ".join(
            CODE_BLOCK_LINES.format(first_line = block.first_line, last_line = block.last_line)
            for block in long_blocks
        )

        return remark.format(file_name = changed_file.path.name, max_lines = max_lines, long_blocks = shown_blocks)

    def hook(context: StepContext) -> str | None:
        """Проверяет изменённые файлы папки."""
        remarks = [
            remark_text
            for changed_file in read_changed_files(context = context, folder = folder)
            if (remark_text := file_remark(changed_file)) is not None
        ]

        return join_remarks(remarks = remarks)

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
