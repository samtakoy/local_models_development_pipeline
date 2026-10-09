"""Тесты разбора команды bash на простые команды."""

from codeteam.common.bash_guard import SimpleCommand, Word, parse_command


def _parse(*, text: str) -> tuple[SimpleCommand, ...]:
    """
    Разбирает команду, которая должна разобраться без ошибки.

        text: текст команды.

    Возвращает: Простые команды.
    """
    commands = parse_command(text = text)
    assert commands is not None

    return commands


def test_chain_is_split_into_simple_commands() -> None:
    """
    Цепочка &&, |, ; делится на простые команды по порядку.
    """
    commands = _parse(text = "cd /x && uv run pytest 2>&1 | tail -5; echo hi")

    assert [command.name.text for command in commands] == ["cd", "uv", "tail", "echo"]


def test_redirect_is_not_argument() -> None:
    """
    Перенаправления не попадают в аргументы.
    """
    (command,) = _parse(text = "kill 123 2>/dev/null > out.txt")

    assert command.arguments == (Word(text = "123", is_literal = True),)


def test_words_after_redirect_are_arguments() -> None:
    """
    Слова после файла перенаправления — аргументы команды.
    """
    (command,) = _parse(text = "kill 2>/dev/null -9 123")

    assert command.arguments == (Word(text = "-9", is_literal = True), Word(text = "123", is_literal = True))


def test_words_after_redirect_of_chain_belong_to_last_command() -> None:
    """
    Слова после перенаправления в конце цепочки — аргументы её последней команды.
    """
    cd_command, kill_command = _parse(text = "cd /x && kill 2>/dev/null 123")

    assert cd_command.arguments == (Word(text = "/x", is_literal = True),)
    assert kill_command.arguments == (Word(text = "123", is_literal = True),)


def test_quoted_arguments_lose_quotes() -> None:
    """
    Аргументы в кавычках видны целиком и без кавычек.
    """
    (command,) = _parse(text = """pkill -f "python src/app.py" 'b' "a"b""")

    assert command.arguments == (
        Word(text = "-f", is_literal = True),
        Word(text = "python src/app.py", is_literal = True),
        Word(text = "b", is_literal = True),
        Word(text = "ab", is_literal = True),
    )


def test_variables_and_substitutions_are_not_literal() -> None:
    """
    Аргументы с переменной или подстановкой не видны целиком; команда подстановки разбирается тоже.
    """
    commands = _parse(text = 'kill $PID "$!" "$(pgrep -f app)"')

    assert [command.name.text for command in commands] == ["kill", "pgrep"]
    assert [argument.is_literal for argument in commands[0].arguments] == [False, False, False]


def test_syntax_error_returns_none() -> None:
    """
    Команда с синтаксической ошибкой не разбирается.
    """
    assert parse_command(text = 'grep "```" docs/a.md') is None
