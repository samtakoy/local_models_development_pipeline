"""Разбор текста команды bash на простые команды: имя и аргументы."""

import shlex
from dataclasses import dataclass

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

_BASH_LANGUAGE = Language(tree_sitter_bash.language())

# Узлы, значение которых известно только при выполнении: переменные, подстановки, вычисления.
_DYNAMIC_NODE_TYPES = {
    "simple_expansion",
    "expansion",
    "command_substitution",
    "process_substitution",
    "arithmetic_expansion",
    "ansi_c_string",
}

# Узлы-группы: перенаправление группы относится ко всем командам внутри.
_GROUP_NODE_TYPES = {"compound_statement", "subshell"}

# Узлы перенаправлений, внутри которых бывают перенаправления в файл.
_INLINE_TEXT_NODE_TYPES = {"heredoc_redirect", "herestring_redirect"}


@dataclass(frozen = True)
class Word:
    """
    Слово команды: имя или аргумент.

        text: значение без кавычек, если оно видно целиком; иначе текст как в команде.
        is_literal: значение видно целиком: нет переменных, подстановок и вычислений.
    """

    text: str
    is_literal: bool


@dataclass(frozen = True)
class SimpleCommand:
    """
    Простая команда: часть цепочки &&, ||, ;, |, группы или подстановки $(...).

        name: имя команды.
        arguments: аргументы по порядку, без перенаправлений.
        text: текст команды.
    """

    name: Word
    arguments: tuple[Word, ...]
    text: str


def parse_command(*, text: str) -> tuple[SimpleCommand, ...] | None:
    """
    Разбирает текст команды bash на простые команды.

        text: текст команды.

    Возвращает: Простые команды в порядке следования в тексте; None, если в тексте синтаксическая ошибка.
    """
    tree = Parser(_BASH_LANGUAGE).parse(text.encode())
    if tree.root_node.has_error:
        return None

    extra_arguments = _collect_extra_arguments(root = tree.root_node)
    commands = []
    for node in _collect_command_nodes(node = tree.root_node):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            continue

        own_arguments = [_make_word(node = argument) for argument in node.children_by_field_name("argument")]
        commands.append(
            SimpleCommand(
                name = _make_word(node = name_node),
                arguments = tuple(own_arguments + extra_arguments.get(node.id, [])),
                text = node.text.decode(),
            )
        )

    return tuple(commands)


def _collect_command_nodes(*, node: Node) -> list[Node]:
    """
    Находит все узлы простых команд в поддереве.

        node: корень поддерева.

    Возвращает: Узлы command в порядке следования в тексте.
    """
    found: list[Node] = []
    if node.type == "command":
        found.append(node)
    for child in node.children:
        found.extend(_collect_command_nodes(node = child))

    return found


def _collect_extra_arguments(*, root: Node) -> dict[int, list[Word]]:
    """
    Находит аргументы, записанные после файла перенаправления: в "kill 2>/dev/null 123" разборщик
    относит 123 к перенаправлению, а для bash это аргумент команды.

        root: корень дерева разбора.

    Возвращает: Словарь: id узла команды → её аргументы из перенаправлений по порядку.
    """
    extra_arguments: dict[int, list[Word]] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "command":
            targets = [node]
        elif node.type == "redirected_statement":
            targets = _redirect_targets(statement = node)
        else:
            continue

        words = _words_after_destination(redirects = node.children_by_field_name("redirect"))
        for target in targets:
            extra_arguments.setdefault(target.id, []).extend(words)

    return extra_arguments


def _redirect_targets(*, statement: Node) -> list[Node]:
    """
    Находит команды, к которым относятся перенаправления узла redirected_statement.

        statement: узел redirected_statement.

    Возвращает:
        Все команды группы для { ... } и ( ... ), иначе последнюю команду тела вне подстановок:
        в bash "a && b > f" перенаправляет только b.
    """
    body = statement.child_by_field_name("body")
    if body is None:
        return []

    if body.type in _GROUP_NODE_TYPES:
        return _collect_command_nodes(node = body)

    commands = [
        command
        for command in _collect_command_nodes(node = body)
        if not _is_inside_substitution(node = command, top = body)
    ]

    return commands[-1:]


def _is_inside_substitution(*, node: Node, top: Node) -> bool:
    """
    Проверяет, лежит ли узел внутри подстановки $(...) ниже узла top.

        node: проверяемый узел.
        top: узел, выше которого не подниматься.

    Возвращает: True, если между node и top есть подстановка команды.
    """
    current = node.parent
    while current is not None and current.id != top.id:
        if current.type == "command_substitution":
            return True
        current = current.parent

    return False


def _words_after_destination(*, redirects: list[Node]) -> list[Word]:
    """
    Собирает слова, записанные после файла перенаправления.

        redirects: узлы перенаправлений; перенаправления в файл внутри встроенного текста
            (cat << EOF > f) тоже просматриваются.

    Возвращает: Слова по порядку.
    """
    words: list[Word] = []
    for redirect in redirects:
        if redirect.type == "file_redirect":
            destinations = redirect.children_by_field_name("destination")
            words.extend(_make_word(node = destination) for destination in destinations[1:])
        elif redirect.type in _INLINE_TEXT_NODE_TYPES:
            nested = [child for child in redirect.children if child.type == "file_redirect"]
            words.extend(_words_after_destination(redirects = nested))

    return words


def _make_word(*, node: Node) -> Word:
    """
    Описывает слово команды.

        node: узел слова: word, string, raw_string, concatenation, number и другие.

    Возвращает: Слово без кавычек, если значение видно целиком, иначе слово с текстом как в команде.
    """
    text = node.text.decode()
    if _has_dynamic_part(node = node):
        return Word(text = text, is_literal = False)

    try:
        tokens = shlex.split(text)
    except ValueError:
        return Word(text = text, is_literal = False)

    if len(tokens) != 1:
        return Word(text = text, is_literal = False)

    return Word(text = tokens[0], is_literal = True)


def _has_dynamic_part(*, node: Node) -> bool:
    """
    Проверяет, есть ли в узле часть, значение которой известно только при выполнении.

        node: узел слова.

    Возвращает: True, если в узле есть переменная, подстановка или вычисление.
    """
    if node.type in _DYNAMIC_NODE_TYPES:
        return True

    return any(_has_dynamic_part(node = child) for child in node.children)
