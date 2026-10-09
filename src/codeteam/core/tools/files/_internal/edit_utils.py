"""Поиск фрагмента old_string в тексте файла и его замена на new_string.

Способы поиска, их порядок и пороги перенесены из opencode (https://github.com/anomalyco/opencode,
packages/opencode/src/tool/edit.ts, коммит 9b4882db54), лицензия MIT; см. THIRD_PARTY_NOTICES.md.

Каждый способ перечисляет куски текста файла, которые считает совпадением с old_string. Замена берёт
первый кусок, который встречается в файле ровно один раз; с replace_all — первый найденный кусок
во всех местах.
"""

import math
import re
from collections.abc import Callable, Iterator

# Наименьшее сходство средних строк куска для поиска по первой и последней строке.
BLOCK_SIMILARITY_THRESHOLD = 0.65

# Доля строк, на которую кусок при поиске по первой и последней строке может отличаться от old_string.
BLOCK_SIZE_TOLERANCE = 0.25

# Доля совпавших средних строк для поиска по первой и последней строке с проверкой середины.
CONTEXT_MATCH_SHARE = 0.5

# Во сколько раз найденный кусок может быть длиннее old_string по строкам.
DISPROPORTION_LINE_FACTOR = 2

# На сколько строк найденный кусок может быть длиннее old_string.
DISPROPORTION_LINE_MARGIN = 3

# Во сколько раз найденный кусок может быть длиннее old_string по знакам.
DISPROPORTION_CHARACTER_FACTOR = 4

# На сколько знаков найденный кусок может быть длиннее old_string.
DISPROPORTION_CHARACTER_MARGIN = 500

# Доля строк old_string, на которую могут расходиться начала, указанные якорями одного места.
ANCHOR_SPREAD_SHARE = 0.25

# Наибольшее число строк места, для которого агенту показывается похожий кусок файла.
SIMILAR_FRAGMENT_LINE_LIMIT = 50

# Сколько строк файла показывается до и после похожего места.
SIMILAR_FRAGMENT_MARGIN = 2

IDENTICAL_STRINGS_MESSAGE = "old_string и new_string совпадают: правка ничего не меняет."

EMPTY_OLD_STRING_MESSAGE = (
    "old_string пуст. Укажи точный текст, который нужно заменить; новый файл создаётся инструментом write."
)

NOT_FOUND_MESSAGE = (
    "old_string не найден в файле. Текст должен совпадать с файлом, включая отступы и переводы строк; "
    "заголовок и номера «N:» из вывода read в него не входят."
)

MULTIPLE_MATCHES_MESSAGE = (
    "old_string найден в нескольких местах. Добавь соседние строки, чтобы место стало единственным, "
    "или задай replace_all, чтобы заменить все."
)

DISPROPORTIONATE_MATCH_MESSAGE = (
    "Найденный кусок намного больше old_string, замена отклонена. Перечитай файл и укажи old_string точно."
)

# Экранированные знаки, которые модель пишет вместо настоящих, и их значения.
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "'": "'", '"': '"', "`": "`", "\\": "\\", "\n": "\n", "$": "$"}

_ESCAPE_PATTERN = re.compile(r"\\(n|t|r|'|\"|`|\\|\n|\$)")

_WHITESPACE_PATTERN = re.compile(r"\s+")

_INDENT_PATTERN = re.compile(r"^(\s*)")

# Способ поиска: по тексту файла и old_string перечисляет куски файла-кандидаты.
Candidates = Callable[..., Iterator[str]]


class TextMatchError(ValueError):
    """Замену нельзя выполнить: old_string не найден, найден неоднозначно или правка пустая."""


class TextNotFoundError(TextMatchError):
    """old_string не найден в тексте ни одним способом поиска."""


def replace_text(*, content: str, old_string: str, new_string: str, replace_all: bool) -> str:
    """
    Заменяет в тексте фрагмент old_string на new_string, перебирая способы поиска по порядку.

        content: текст файла с переводами строк \\n.
        old_string: фрагмент, который нужно заменить.
        new_string: текст на замену.
        replace_all: заменить все вхождения найденного куска.

    Возвращает: Текст после замены. Отказ поднимает TextMatchError, для ненайденного old_string —
        TextNotFoundError.
    """
    if old_string == new_string:
        raise TextMatchError(IDENTICAL_STRINGS_MESSAGE)

    if not old_string:
        raise TextMatchError(EMPTY_OLD_STRING_MESSAGE)

    is_found = False
    for candidates in _SEARCH_CHAIN:
        for search in candidates(content = content, find = old_string):
            index = content.find(search)
            if index == -1:
                continue

            is_found = True
            if _is_disproportionate_match(search = search, old_string = old_string):
                raise TextMatchError(DISPROPORTIONATE_MATCH_MESSAGE)

            if replace_all:
                return content.replace(search, new_string)

            if index != content.rfind(search):
                continue

            return content[:index] + new_string + content[index + len(search):]

    if not is_found:
        raise TextNotFoundError(NOT_FOUND_MESSAGE)

    raise TextMatchError(MULTIPLE_MATCHES_MESSAGE)


def similar_fragment(*, content: str, old_string: str) -> tuple[int, int] | None:
    """
    Ищет единственное место файла, на которое указывают якоря: строки old_string, которые
    встречаются в файле ровно один раз (без пробелов по краям).

    Каждый якорь указывает начало места: свой номер в файле минус свой номер в old_string.
    Место — от самого раннего начала до самого позднего начала плюс длина old_string, с запасом
    SIMILAR_FRAGMENT_MARGIN строк с каждой стороны.

        content: текст файла с переводами строк \\n.
        old_string: фрагмент от модели.

    Возвращает: Номера первой и последней строки места с запасом, от 1; None, если якорей нет,
        они указывают в разные места или место длиннее SIMILAR_FRAGMENT_LINE_LIMIT строк.
    """
    content_lines = content.split("\n")
    old_lines = _without_trailing_empty_line(lines = old_string.split("\n"))

    # номера строк файла для каждого текста строки
    line_numbers: dict[str, list[int]] = {}
    for number, line in enumerate(content_lines):
        if line.strip():
            line_numbers.setdefault(line.strip(), []).append(number)

    # начало места по каждому якорю
    starts = []
    for old_number, line in enumerate(old_lines):
        found = line_numbers.get(line.strip(), [])
        if len(found) == 1:
            starts.append(found[0] - old_number)

    if not starts:
        return None

    spread = max(starts) - min(starts)
    allowed_spread = max(1, math.floor(len(old_lines) * ANCHOR_SPREAD_SHARE))
    # якоря указывают в разные места
    if spread > allowed_spread:
        return None

    if max(starts) + len(old_lines) - min(starts) > SIMILAR_FRAGMENT_LINE_LIMIT:
        return None

    first_index = max(0, min(starts) - SIMILAR_FRAGMENT_MARGIN)
    last_index = min(len(content_lines) - 1, max(starts) + len(old_lines) - 1 + SIMILAR_FRAGMENT_MARGIN)

    return first_index + 1, last_index + 1


def levenshtein(*, first: str, second: str) -> int:
    """
    Считает расстояние Левенштейна: сколько знаков вставить, удалить или заменить.

        first: первая строка.
        second: вторая строка.

    Возвращает: Число правок.
    """
    if not first or not second:
        return max(len(first), len(second))

    previous_row = list(range(len(second) + 1))
    for first_index, first_character in enumerate(first, start = 1):
        current_row = [first_index]
        for second_index, second_character in enumerate(second, start = 1):
            cost = 0 if first_character == second_character else 1
            current_row.append(
                min(
                    previous_row[second_index] + 1,
                    current_row[second_index - 1] + 1,
                    previous_row[second_index - 1] + cost,
                )
            )

        previous_row = current_row

    return previous_row[-1]


def simple_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Точное совпадение.

        content: текст файла.
        find: old_string.

    Возвращает: Сам old_string.
    """
    yield find


def line_trimmed_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Строки файла, совпадающие с old_string без пробелов по краям каждой строки.

        content: текст файла.
        find: old_string.

    Возвращает: Куски файла по совпавшим строкам.
    """
    content_lines = content.split("\n")
    search_lines = _without_trailing_empty_line(lines = find.split("\n"))
    for first_index in range(len(content_lines) - len(search_lines) + 1):
        block = content_lines[first_index:first_index + len(search_lines)]
        if all(line.strip() == search.strip() for line, search in zip(block, search_lines, strict = True)):
            yield "\n".join(block)


def block_anchor_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Кусок от 3 строк: первая и последняя строки совпадают без пробелов по краям, средние похожи.

    Размер куска отличается от old_string не больше чем на BLOCK_SIZE_TOLERANCE строк; сходство средних
    строк по расстоянию Левенштейна не меньше BLOCK_SIMILARITY_THRESHOLD. Из нескольких кусков берётся
    самый похожий.

        content: текст файла.
        find: old_string.

    Возвращает: Не больше одного куска файла.
    """
    content_lines = content.split("\n")
    search_lines = find.split("\n")
    if len(search_lines) < 3:
        return

    search_lines = _without_trailing_empty_line(lines = search_lines)
    first_search = search_lines[0].strip()
    last_search = search_lines[-1].strip()
    max_size_delta = max(1, math.floor(len(search_lines) * BLOCK_SIZE_TOLERANCE))
    spans: list[tuple[int, int]] = []
    for first_index, line in enumerate(content_lines):
        if line.strip() != first_search:
            continue

        for last_index in range(first_index + 2, len(content_lines)):
            if content_lines[last_index].strip() == last_search:
                if abs(last_index - first_index + 1 - len(search_lines)) <= max_size_delta:
                    spans.append((first_index, last_index))

                break

    if not spans:
        return

    if len(spans) == 1:
        first_index, last_index = spans[0]
        similarity = _single_span_similarity(
            content_lines = content_lines,
            search_lines = search_lines,
            first_index = first_index,
            last_index = last_index,
        )
        if similarity >= BLOCK_SIMILARITY_THRESHOLD:
            yield "\n".join(content_lines[first_index:last_index + 1])

        return

    best_span: tuple[int, int] | None = None
    best_similarity = -1.0
    for first_index, last_index in spans:
        similarity = _average_span_similarity(
            content_lines = content_lines,
            search_lines = search_lines,
            first_index = first_index,
            last_index = last_index,
        )
        if similarity > best_similarity:
            best_similarity = similarity
            best_span = (first_index, last_index)

    if best_span is not None and best_similarity >= BLOCK_SIMILARITY_THRESHOLD:
        yield "\n".join(content_lines[best_span[0]:best_span[1] + 1])


def whitespace_normalized_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Строки и куски файла, совпадающие с old_string, если свести любые пробелы к одному.

        content: текст файла.
        find: old_string.

    Возвращает: Строки, части строк и многострочные куски файла.
    """
    normalized_find = _normalize_whitespace(text = find)
    content_lines = content.split("\n")
    for line in content_lines:
        normalized_line = _normalize_whitespace(text = line)
        if normalized_line == normalized_find:
            yield line
        elif normalized_find in normalized_line:
            words = find.split()
            if words:
                match = re.search(r"\s+".join(re.escape(word) for word in words), line)
                if match is not None:
                    yield match.group(0)

    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for first_index in range(len(content_lines) - len(find_lines) + 1):
            block = "\n".join(content_lines[first_index:first_index + len(find_lines)])
            if _normalize_whitespace(text = block) == normalized_find:
                yield block


def indentation_flexible_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Куски файла, совпадающие с old_string без общего отступа.

        content: текст файла.
        find: old_string.

    Возвращает: Куски файла той же длины в строках.
    """
    normalized_find = _remove_common_indent(text = find)
    content_lines = content.split("\n")
    find_line_count = len(find.split("\n"))
    for first_index in range(len(content_lines) - find_line_count + 1):
        block = "\n".join(content_lines[first_index:first_index + find_line_count])
        if _remove_common_indent(text = block) == normalized_find:
            yield block


def escape_normalized_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Совпадение после замены экранированных знаков (\\n, \\t, \\") на настоящие.

        content: текст файла.
        find: old_string.

    Возвращает: old_string без экранирования и куски файла, совпадающие с ним после того же преобразования.
    """
    unescaped_find = _unescape(text = find)
    if unescaped_find in content:
        yield unescaped_find

    content_lines = content.split("\n")
    find_line_count = len(unescaped_find.split("\n"))
    for first_index in range(len(content_lines) - find_line_count + 1):
        block = "\n".join(content_lines[first_index:first_index + find_line_count])
        if _unescape(text = block) == unescaped_find:
            yield block


def trimmed_boundary_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Совпадение old_string без пустоты в начале и конце.

        content: текст файла.
        find: old_string.

    Возвращает: old_string без пустоты по краям и куски файла, совпадающие с ним без пустоты по краям.
    """
    trimmed_find = find.strip()
    if trimmed_find == find:
        return

    if trimmed_find in content:
        yield trimmed_find

    content_lines = content.split("\n")
    find_line_count = len(find.split("\n"))
    for first_index in range(len(content_lines) - find_line_count + 1):
        block = "\n".join(content_lines[first_index:first_index + find_line_count])
        if block.strip() == trimmed_find:
            yield block


def context_aware_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Кусок от 3 строк той же длины: первая и последняя строки совпадают без пробелов по краям,
    из непустых средних строк совпадает не меньше CONTEXT_MATCH_SHARE.

        content: текст файла.
        find: old_string.

    Возвращает: Для каждой совпавшей первой строки — не больше одного куска файла.
    """
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return

    find_lines = _without_trailing_empty_line(lines = find_lines)
    content_lines = content.split("\n")
    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()
    for first_index, line in enumerate(content_lines):
        if line.strip() != first_line:
            continue

        for last_index in range(first_index + 2, len(content_lines)):
            if content_lines[last_index].strip() != last_line:
                continue

            block_lines = content_lines[first_index:last_index + 1]
            if len(block_lines) == len(find_lines) and _middle_lines_match(
                block_lines = block_lines,
                find_lines = find_lines,
            ):
                yield "\n".join(block_lines)

            break


def multi_occurrence_candidates(*, content: str, find: str) -> Iterator[str]:
    """
    Точное совпадение по разу на каждое вхождение old_string.

        content: текст файла.
        find: old_string.

    Возвращает: old_string столько раз, сколько он встречается в файле.
    """
    start = 0
    while True:
        index = content.find(find, start)
        if index == -1:
            return

        yield find
        start = index + len(find)


# Способы поиска в порядке перебора.
_SEARCH_CHAIN: tuple[Candidates, ...] = (
    simple_candidates,
    line_trimmed_candidates,
    block_anchor_candidates,
    whitespace_normalized_candidates,
    indentation_flexible_candidates,
    escape_normalized_candidates,
    trimmed_boundary_candidates,
    context_aware_candidates,
    multi_occurrence_candidates,
)


def _is_disproportionate_match(*, search: str, old_string: str) -> bool:
    """
    Проверяет, что найденный кусок намного больше old_string.

        search: найденный кусок файла.
        old_string: фрагмент от модели.

    Возвращает: True, если кусок длиннее по строкам в DISPROPORTION_LINE_FACTOR раз
        или на DISPROPORTION_LINE_MARGIN строк; для многострочного old_string — ещё и по знакам.
    """
    old_line_count = len(old_string.split("\n"))
    search_line_count = len(search.split("\n"))
    line_limit = max(old_line_count + DISPROPORTION_LINE_MARGIN, old_line_count * DISPROPORTION_LINE_FACTOR)
    if search_line_count >= line_limit:
        return True

    if old_line_count == 1:
        return False

    old_length = len(old_string.strip())
    character_limit = max(
        old_length + DISPROPORTION_CHARACTER_MARGIN,
        old_length * DISPROPORTION_CHARACTER_FACTOR,
    )

    return len(search.strip()) > character_limit


def _single_span_similarity(
    *,
    content_lines: list[str],
    search_lines: list[str],
    first_index: int,
    last_index: int,
) -> float:
    """
    Считает сходство средних строк единственного куска; счёт останавливается, как только набран порог.

        content_lines: строки файла.
        search_lines: строки old_string.
        first_index: индекс первой строки куска.
        last_index: индекс последней строки куска.

    Возвращает: Сходство от 0 до 1; 1, если средних строк нет.
    """
    span_size = last_index - first_index + 1
    lines_to_check = min(len(search_lines) - 2, span_size - 2)
    if lines_to_check <= 0:
        return 1.0

    similarity = 0.0
    for offset in range(1, min(len(search_lines) - 1, span_size - 1)):
        line_similarity = _line_similarity(
            content_line = content_lines[first_index + offset],
            search_line = search_lines[offset],
        )
        if line_similarity is None:
            continue

        similarity += line_similarity / lines_to_check
        if similarity >= BLOCK_SIMILARITY_THRESHOLD:
            break

    return similarity


def _average_span_similarity(
    *,
    content_lines: list[str],
    search_lines: list[str],
    first_index: int,
    last_index: int,
) -> float:
    """
    Считает среднее сходство средних строк куска.

        content_lines: строки файла.
        search_lines: строки old_string.
        first_index: индекс первой строки куска.
        last_index: индекс последней строки куска.

    Возвращает: Сходство от 0 до 1; 1, если средних строк нет.
    """
    span_size = last_index - first_index + 1
    lines_to_check = min(len(search_lines) - 2, span_size - 2)
    if lines_to_check <= 0:
        return 1.0

    similarity = 0.0
    for offset in range(1, min(len(search_lines) - 1, span_size - 1)):
        line_similarity = _line_similarity(
            content_line = content_lines[first_index + offset],
            search_line = search_lines[offset],
        )
        if line_similarity is not None:
            similarity += line_similarity

    return similarity / lines_to_check


def _line_similarity(*, content_line: str, search_line: str) -> float | None:
    """
    Считает сходство двух строк без пробелов по краям.

        content_line: строка файла.
        search_line: строка old_string.

    Возвращает: 1 минус доля правок от длины более длинной строки; None, если обе строки пусты.
    """
    content_text = content_line.strip()
    search_text = search_line.strip()
    longest = max(len(content_text), len(search_text))
    if longest == 0:
        return None

    return 1 - levenshtein(first = content_text, second = search_text) / longest


def _middle_lines_match(*, block_lines: list[str], find_lines: list[str]) -> bool:
    """
    Проверяет, что из непустых средних строк совпадает не меньше CONTEXT_MATCH_SHARE.

        block_lines: строки куска файла.
        find_lines: строки old_string той же длины.

    Возвращает: True, если непустых средних строк нет или совпавших достаточно.
    """
    matching = 0
    non_empty = 0
    for block_line, find_line in zip(block_lines[1:-1], find_lines[1:-1], strict = True):
        block_text = block_line.strip()
        find_text = find_line.strip()
        if block_text or find_text:
            non_empty += 1
            if block_text == find_text:
                matching += 1

    return non_empty == 0 or matching / non_empty >= CONTEXT_MATCH_SHARE


def _without_trailing_empty_line(*, lines: list[str]) -> list[str]:
    """
    Убирает пустую последнюю строку, которую даёт перевод строки в конце old_string.

        lines: строки old_string.

    Возвращает: Строки без пустой последней.
    """
    if len(lines) > 1 and lines[-1] == "":
        return lines[:-1]

    return lines


def _normalize_whitespace(*, text: str) -> str:
    """
    Сводит любые пробелы к одному и убирает пробелы по краям.

        text: текст.

    Возвращает: Текст с одиночными пробелами.
    """
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _remove_common_indent(*, text: str) -> str:
    """
    Убирает общий отступ непустых строк.

        text: текст.

    Возвращает: Текст без общего отступа; пустые строки не меняются.
    """
    lines = text.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        return text

    common_indent = min(len(_INDENT_PATTERN.match(line).group(1)) for line in non_empty_lines)

    return "\n".join(line if not line.strip() else line[common_indent:] for line in lines)


def _unescape(*, text: str) -> str:
    """
    Заменяет экранированные знаки на настоящие.

        text: текст.

    Возвращает: Текст без экранирования.
    """
    return _ESCAPE_PATTERN.sub(lambda match: _ESCAPES[match.group(1)], text)
