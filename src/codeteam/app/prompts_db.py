"""База промптов: копии версий файлов промптов и список версий, с которыми запущен прогон.

Копия лежит в базе по тому же пути, что и файл относительно папки промптов, под именем
<имя файла>.<дата изменения ГГММДД>.<отпечаток>, например roles/senior/prompts.py.261010.<отпечаток>.
Копия с таким именем уже есть - версия сохранена раньше, новая копия не создаётся.
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import codeteam.core

# Папка промптов: пути файлов промптов в базе и в списке прогона считаются от неё.
PROMPTS_ROOT = Path(codeteam.core.__file__).parent

# Шаблоны путей файлов промптов относительно папки промптов.
PROMPT_FILE_PATTERNS = (
    "agent/prompts.py",
    "roles/**/prompts.py",
    "roles/*/system_prompt.md",
    "tools/**/*_prompts.py",
)

# Сколько первых знаков отпечатка sha256 содержимого входит в имя копии.
FINGERPRINT_LENGTH = 20

# Вид даты изменения файла в имени копии.
DATE_FORMAT = "%y%m%d"

# Файл в папке прогона: какие копии промптов были в прогоне.
RUN_PROMPTS_FILE_NAME = "prompts.md"


def save_prompts(*, prompts_root: Path, db_dir: Path, run_dir: Path) -> Path:
    """
    Сохраняет в базу версии файлов промптов, которых там ещё нет, и пишет в папку прогона список копий.

        prompts_root: папка промптов.
        db_dir: папка базы промптов.
        run_dir: папка прогона.

    Возвращает: Путь файла со списком копий в папке прогона.
    """
    copies: list[tuple[Path, Path]] = []
    for source in find_prompt_files(prompts_root = prompts_root):
        relative_path = source.relative_to(prompts_root)
        copy_path = relative_path.with_name(build_copy_name(source = source))
        target = db_dir / copy_path
        if not target.exists():
            target.parent.mkdir(parents = True, exist_ok = True)
            shutil.copy2(source, target)
        copies.append((relative_path, copy_path))

    run_dir.mkdir(parents = True, exist_ok = True)
    list_path = run_dir / RUN_PROMPTS_FILE_NAME
    list_path.write_text(
        _render_copies(prompts_root = prompts_root, db_dir = db_dir, copies = copies),
        encoding = "utf-8",
    )

    return list_path


def find_prompt_files(*, prompts_root: Path) -> list[Path]:
    """
    Находит файлы промптов по шаблонам PROMPT_FILE_PATTERNS.

        prompts_root: папка промптов.

    Возвращает: Пути файлов промптов без повторов, по алфавиту.
    """
    found = {
        path
        for pattern in PROMPT_FILE_PATTERNS
        for path in prompts_root.glob(pattern)
        if path.is_file()
    }

    return sorted(found)


def build_copy_name(*, source: Path) -> str:
    """
    Собирает имя копии файла промптов: имя файла, дата изменения и отпечаток содержимого.

        source: файл промптов.

    Возвращает: Имя вида prompts.py.261010.<отпечаток>.
    """
    modified_date = datetime.fromtimestamp(source.stat().st_mtime).strftime(DATE_FORMAT)
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()[:FINGERPRINT_LENGTH]

    return f"{source.name}.{modified_date}.{fingerprint}"


def _render_copies(*, prompts_root: Path, db_dir: Path, copies: list[tuple[Path, Path]]) -> str:
    """
    Собирает текст списка копий промптов прогона.

        prompts_root: папка промптов.
        db_dir: папка базы промптов.
        copies: пары путей: файл относительно папки промптов и его копия относительно папки базы.

    Возвращает: Текст в разметке markdown: папки и таблица «файл - копия».
    """
    lines = [
        "# Промпты прогона",
        "",
        f"- папка промптов: `{prompts_root}`",
        f"- база промптов: `{db_dir}`",
        "",
        "| Файл | Копия в базе |",
        "|---|---|",
    ]
    lines.extend(f"| {file_path.as_posix()} | {copy_path.as_posix()} |" for file_path, copy_path in copies)

    return "\n".join(lines) + "\n"
