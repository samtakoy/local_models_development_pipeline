"""Тесты поиска и замены текста для edit и поиска похожего места файла."""

import re

import pytest

from codeteam.core.tools.files._internal.edit_utils import (
    DISPROPORTIONATE_MATCH_MESSAGE,
    EMPTY_OLD_STRING_MESSAGE,
    IDENTICAL_STRINGS_MESSAGE,
    MULTIPLE_MATCHES_MESSAGE,
    NOT_FOUND_MESSAGE,
    SIMILAR_FRAGMENT_LINE_LIMIT,
    TextMatchError,
    context_aware_candidates,
    indentation_flexible_candidates,
    levenshtein,
    replace_text,
    similar_fragment,
    trimmed_boundary_candidates,
)

# Файл для поиска похожего места: номера строк от 1 — в комментариях.
FUNCTIONS_CONTENT = "\n".join([
    "def first():",       # 1
    "    return 1",       # 2
    "",                   # 3
    "def second():",      # 4
    "    value = 2",      # 5
    "    return value",   # 6
    "",                   # 7
    "def third():",       # 8
    "    return 3",       # 9
])


def _replace(*, content: str, old_string: str, new_string: str) -> str:
    """
    Заменяет единственное вхождение.

        content: текст файла.
        old_string: фрагмент, который нужно заменить.
        new_string: текст на замену.

    Возвращает: Текст после замены.
    """
    return replace_text(
        content = content,
        old_string = old_string,
        new_string = new_string,
        replace_all = False,
    )


def test_levenshtein_counts_edits() -> None:
    """
    Расстояние Левенштейна: замена знака, пустая строка, классический пример.
    """
    assert levenshtein(first = "x = 1", second = "x = 2") == 1
    assert levenshtein(first = "", second = "abc") == 3
    assert levenshtein(first = "kitten", second = "sitting") == 3


def test_exact_match_is_replaced() -> None:
    """
    Точное совпадение заменяется.
    """
    result = _replace(content = "a = 1\nb = 2\n", old_string = "b = 2", new_string = "b = 3")

    assert result == "a = 1\nb = 3\n"


def test_lines_match_without_edge_spaces() -> None:
    """
    Строки находятся без пробелов по краям; заменяется весь кусок файла вместе с отступом.
    """
    content = "def run():\n    a = 1\n    b = 2\n"

    result = _replace(content = content, old_string = "a = 1\nb = 2", new_string = "    a = 10\n    b = 20")

    assert result == "def run():\n    a = 10\n    b = 20\n"


def test_block_with_similar_middle_is_replaced() -> None:
    """
    Кусок с совпавшими первой и последней строками и похожей серединой заменяется.
    """
    content = "def run():\n    total = compute(values)\n    return total\n"
    old_string = "def run():\n    total = compute(value)\n    return total"

    result = _replace(content = content, old_string = old_string, new_string = "def run():\n    return 0")

    assert result == "def run():\n    return 0\n"


@pytest.mark.parametrize(
    "content",
    [
        "function configure() {\n  keepImportantState()\n  removeAllUserData()\n"
        "  archiveBackups()\n  auditLog()\n}",
        "function configure() {\n  removeAllUserData()\n}",
    ],
)
def test_block_with_unrelated_middle_is_not_found(content: str) -> None:
    """
    Кусок с чужой серединой или другого размера не находится, файл не меняется (случаи из opencode).
    """
    with pytest.raises(TextMatchError, match = re.escape(NOT_FOUND_MESSAGE)):
        _replace(
            content = content,
            old_string = "function configure() {\n  const enabled = true\n}",
            new_string = "function configure() {\n  const enabled = false\n}",
        )


def test_inner_spaces_are_normalized() -> None:
    """
    Любые пробелы внутри строки сводятся к одному.
    """
    assert _replace(content = "x  =   1\n", old_string = "x = 1", new_string = "x = 2") == "x = 2\n"


def test_common_indent_is_ignored() -> None:
    """
    Кусок находится без общего отступа.
    """
    content = "class Job:\n        if ok:\n            run()\n"

    candidates = list(indentation_flexible_candidates(content = content, find = "if ok:\n    run()"))

    assert candidates == ["        if ok:\n            run()"]


def test_escaped_characters_are_unescaped() -> None:
    """
    Экранированные кавычки в old_string совпадают с настоящими.
    """
    result = _replace(content = 'print("a")\n', old_string = 'print(\\"a\\")', new_string = 'print("b")')

    assert result == 'print("b")\n'


def test_edge_blank_is_trimmed() -> None:
    """
    Пустота в начале и конце old_string отбрасывается.
    """
    candidates = list(trimmed_boundary_candidates(content = "a\nvalue = 1\nb", find = "\n  value = 1  \n"))

    assert candidates[0] == "value = 1"


def test_context_block_with_half_middle_matched() -> None:
    """
    Кусок той же длины находится, если совпала хотя бы половина непустых средних строк.
    """
    candidates = list(context_aware_candidates(content = "a\nb\nc\nd\ne", find = "a\nb\nX\nd\ne"))

    assert candidates == ["a\nb\nc\nd\ne"]


def test_missing_text_is_refused() -> None:
    """
    Отсутствующий фрагмент — отказ «не найден».
    """
    with pytest.raises(TextMatchError, match = re.escape(NOT_FOUND_MESSAGE)):
        _replace(content = "a = 1\n", old_string = "b = 2", new_string = "b = 3")


def test_several_matches_are_refused_or_replaced_all() -> None:
    """
    Несколько вхождений — отказ; с replace_all заменяются все.
    """
    content = "x = 1\ny = 2\nx = 1\n"

    with pytest.raises(TextMatchError, match = re.escape(MULTIPLE_MATCHES_MESSAGE)):
        _replace(content = content, old_string = "x = 1", new_string = "x = 5")

    result = replace_text(content = content, old_string = "x = 1", new_string = "x = 5", replace_all = True)

    assert result == "x = 5\ny = 2\nx = 5\n"


def test_disproportionate_match_is_refused() -> None:
    """
    Найденный кусок намного длиннее old_string по строкам — отказ.
    """
    with pytest.raises(TextMatchError, match = re.escape(DISPROPORTIONATE_MATCH_MESSAGE)):
        _replace(content = "a\nb\nc\nd", old_string = "a\\nb\\nc\\nd", new_string = "x")


def test_identical_and_empty_strings_are_refused() -> None:
    """
    Совпадающие old_string и new_string и пустой old_string — отказ.
    """
    with pytest.raises(TextMatchError, match = re.escape(IDENTICAL_STRINGS_MESSAGE)):
        _replace(content = "a\n", old_string = "a", new_string = "a")

    with pytest.raises(TextMatchError, match = re.escape(EMPTY_OLD_STRING_MESSAGE)):
        _replace(content = "a\n", old_string = "", new_string = "b")


@pytest.mark.parametrize(
    "old_string",
    [
        # изменена средняя строка
        "def second():\n    value = compute_everything()\n    return value",
        # пропущена средняя строка
        "def second():\n    return value",
        # изменена первая строка
        "def secnd():\n    value = 2\n    return value",
    ],
)
def test_similar_fragment_shows_place_with_margin(old_string: str) -> None:
    """
    Место по якорям — строки 4-6 вместе с изменённой или пропущенной строкой, с запасом в две строки: 2-8.
    """
    assert similar_fragment(content = FUNCTIONS_CONTENT, old_string = old_string) == (2, 8)


def test_similar_fragment_margin_stops_at_file_start() -> None:
    """
    Запас не выходит за начало файла.
    """
    fragment = similar_fragment(content = FUNCTIONS_CONTENT, old_string = "def first():\n    return 10")

    assert fragment == (1, 4)


@pytest.mark.parametrize(
    ("content", "old_string"),
    [
        # якорей нет: таких строк в файле нет
        (FUNCTIONS_CONTENT, "class Missing:\n    pass"),
        # якоря указывают в разные места
        (FUNCTIONS_CONTENT, "def first():\n    return 3"),
        # строки встречаются в файле дважды: якорями не считаются
        ("x = 1\ny = 2\n\nx = 1\ny = 2", "x = 1\ny = 3"),
    ],
)
def test_similar_fragment_without_single_place(content: str, old_string: str) -> None:
    """
    Нет якорей, якоря в разных местах или строки повторяются — похожего места нет.
    """
    assert similar_fragment(content = content, old_string = old_string) is None


def test_similar_fragment_longer_than_limit() -> None:
    """
    Место длиннее SIMILAR_FRAGMENT_LINE_LIMIT строк не показывается.
    """
    content_lines = [f"line {number}" for number in range(SIMILAR_FRAGMENT_LINE_LIMIT * 2)]
    old_lines = content_lines[:SIMILAR_FRAGMENT_LINE_LIMIT + 1]
    old_lines[1] = "changed"

    fragment = similar_fragment(content = "\n".join(content_lines), old_string = "\n".join(old_lines))

    assert fragment is None
