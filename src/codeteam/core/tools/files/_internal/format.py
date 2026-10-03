"""Вид файла для агента: заголовок [путь], строки с номерами."""


def format_header(*, path: str) -> str:
    """
    Собирает заголовок файла для вывода read и write.

        path: путь файла для агента.

    Возвращает: Заголовок вида [путь].
    """
    return f"[{path}]"


def format_line(*, number: int, text: str) -> str:
    """
    Собирает строку файла с номером для вывода агенту.

        number: номер строки, от 1.
        text: текст строки.

    Возвращает: Строку вида "номер:текст".
    """
    return f"{number}:{text}"

def parse_header(*, line: str) -> str | None:
    """
    Разбирает заголовок [путь].

        line: строка правки.

    Возвращает: Путь или None; None, если строка не заголовок.
    """
    trimmed = line.rstrip()
    if not (trimmed.startswith("[") and trimmed.endswith("]")) or len(trimmed) < 2:
        return None

    body = trimmed[1:-1]
    if not body:
        return None

    if has_orphan_bracket(path = body):
        return None

    return body


def has_orphan_bracket(*, path: str) -> bool:
    """
    Проверяет, что в пути есть закрывающая скобка без открывающей.

    Путь может содержать скобки (app/[slug]/page.tsx), но лишняя ] значит, что в строке
    две группы в скобках, а не один заголовок.

        path: путь из заголовка.

    Возвращает: True, если нашлась лишняя ].
    """
    depth = 0
    for character in path:
        if character == "[":
            depth += 1
        elif character == "]":
            if depth == 0:
                return True

            depth -= 1

    return False

