"""Работа с файлами проекта: строки, нумерация, список папки, сведения о файлах, правила пропуска."""

from codeteam.common.files.ignore import IgnoreRules, load_ignore_rules, visible_files
from codeteam.common.files.text_lines import (
    DirectoryEntry,
    FileKind,
    FileStats,
    NumberedPage,
    decode_text,
    file_stats,
    list_directory,
    number_lines,
    split_lines,
)

__all__ = [
    "DirectoryEntry",
    "FileKind",
    "FileStats",
    "IgnoreRules",
    "NumberedPage",
    "decode_text",
    "file_stats",
    "list_directory",
    "load_ignore_rules",
    "number_lines",
    "split_lines",
    "visible_files",
]
