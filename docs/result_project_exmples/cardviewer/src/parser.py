"""Card pack file parser.

Parses text files with flashcard decks according to the spec in docs/card_pack_specs.md.
"""

import re
from dataclasses import dataclass, field


@dataclass
class Card:
    """A single flash card with question, optional answer, and tags."""
    question: str
    answer: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class CardPackInfo:
    """Metadata for a complete card pack (deck)."""
    title: str
    description: str
    date: str | None = None
    cards: list[Card] = field(default_factory=list)


_KEYWORD_PATTERN = re.compile(r'^(date:|title:|desc:)')


def _is_keyword_line(line: str) -> bool:
    """Check if line starts with a recognized header keyword at column 0."""
    return bool(_KEYWORD_PATTERN.match(line))


def parse_card_pack(file_path: str) -> CardPackInfo:
    """Parse a card pack text file.

    Args:
        file_path: Path to the UTF-8 text file with the card pack format.

    Returns:
        A CardPackInfo with extracted metadata and cards.
    """
    with open(file_path, encoding='utf-8') as f:
        content = f.read()

    # Normalize line endings
    content = content.replace('\r\n', '\n')

    # Split header from card blocks on 'q:' at start of lines
    parts = re.split(r'^q:', content, flags=re.MULTILINE)

    if len(parts) == 0:
        return CardPackInfo(title='', description='', date=None, cards=[])

    header = parts[0]
    card_blocks = parts[1:]

    # Parse header
    title, description, date = _parse_header(header)

    # Parse cards
    cards = []
    for block_text in card_blocks:
        if 'a:' in block_text:
            question, answer, tags = _parse_card_block_with_answer(block_text)
            card = Card(question=question, answer=answer, tags=tags)
        else:
            question, tags = _parse_card_block_no_answer(block_text)
            card = Card(question=question, answer=None, tags=tags)
        cards.append(card)

    return CardPackInfo(
        title=title,
        description=description,
        date=date,
        cards=cards,
    )


def parse_card_pack_from_string(content: str) -> CardPackInfo:
    """Parse card pack content from a string directly.

    Useful for testing and internal use.

    Args:
        content: The raw card pack text content.

    Returns:
        A CardPackInfo with extracted metadata and cards.
    """
    # Normalize line endings
    content = content.replace('\r\n', '\n')

    # Split header from card blocks on 'q:' at start of lines
    parts = re.split(r'^q:', content, flags=re.MULTILINE)

    if len(parts) == 0:
        return CardPackInfo(title='', description='', date=None, cards=[])

    header = parts[0]
    card_blocks = parts[1:]

    # Parse header
    title, description, date = _parse_header(header)

    # Parse cards
    cards = []
    for block_text in card_blocks:
        if 'a:' in block_text:
            question, answer, tags = _parse_card_block_with_answer(block_text)
            card = Card(question=question, answer=answer, tags=tags)
        else:
            question, tags = _parse_card_block_no_answer(block_text)
            card = Card(question=question, answer=None, tags=tags)
        cards.append(card)

    return CardPackInfo(
        title=title,
        description=description,
        date=date,
        cards=cards,
    )


def _parse_header(header: str) -> tuple[str, str, str | None]:
    """Parse header section to extract title, description, and date.

    Algorithm:
    - Scan lines for keywords (date:, title:, desc:) at start of lines.
    - For each keyword found, extract content from the same line (after ':')
      and subsequent lines until hitting a blank line or another keyword.
    - Blank/whitespace-only lines are skipped during collection but do not
      terminate it.

    Args:
        header: The text before the first 'q:' marker.

    Returns:
        Tuple of (title, description, date).
    """
    lines = header.split('\n')

    # Find positions of all keywords in order, keeping only first occurrence
    keyword_positions: list[tuple[int, str]] = []
    seen_keywords: set[str] = set()
    for i, line in enumerate(lines):
        if _is_keyword_line(line):
            matched = _KEYWORD_PATTERN.match(line)
            if matched:
                kw = matched.group(1)
                if kw not in seen_keywords:
                    keyword_positions.append((i, kw))
                    seen_keywords.add(kw)

    # Collect values for each keyword into its own list
    title_lines: list[str] = []
    desc_lines: list[str] = []
    date_lines: list[str] = []

    for start_idx, kw in keyword_positions:
        lines_list: list[str] = []

        # Check same line: extract content after the keyword marker
        keyword_line = lines[start_idx]
        matched = _KEYWORD_PATTERN.match(keyword_line)
        if matched:
            keyword_text_len = len(matched.group(1))  # e.g., len("date:") == 5
            rest_of_line = keyword_line[keyword_text_len:]
            if rest_of_line.strip():
                lines_list.append(rest_of_line)

        # Collect from subsequent lines until next keyword or end of file
        for j in range(start_idx + 1, len(lines)):
            if _is_keyword_line(lines[j]):
                break  # Next keyword ends collection
            stripped = lines[j].strip()
            if stripped == '':
                continue  # Skip blank/whitespace-only lines (don't terminate)
            lines_list.append(lines[j])

        # Always store the accumulated lines into the appropriate global list
        if kw == 'date:':
            date_lines.extend(lines_list)
        elif kw == 'title:':
            title_lines.extend(lines_list)
        elif kw == 'desc:':
            desc_lines.extend(lines_list)

    # Build final values
    date = '\n'.join(date_lines).strip() if date_lines else None
    title = '\n'.join(title_lines).strip()
    description = '\n'.join(desc_lines).strip()

    return title, description, date


def _parse_card_block_with_answer(block_text: str) -> tuple[str, str, list[str]]:
    """Parse a card block that contains both question and answer.

    Args:
        block_text: Text of the card block (after 'q:' split).

    Returns:
        Tuple of (question, answer, tags).
    """
    # Find first occurrence of 'a:' at column 0 (start of line)
    match = re.search(r'^a:', block_text, flags=re.MULTILINE)
    if match is None:
        return block_text.strip(), '', []

    question_part = block_text[:match.start()].strip()
    answer_raw = block_text[match.end():]

    # Extract tags from last non-empty line of answer
    tags, clean_answer = _extract_tags(answer_raw)

    return question_part, clean_answer.strip(), tags


def _parse_card_block_no_answer(block_text: str) -> tuple[str, list[str]]:
    """Parse a card block that has no answer section.

    Args:
        block_text: Text of the card block (after 'q:' split).

    Returns:
        Tuple of (question, tags).
    """
    question = block_text.strip()
    return question, []


def _extract_tags(text: str) -> tuple[list[str], str]:
    """Extract tags from the last non-empty line of text.

    If the last non-empty line starts with '#', split it into tags
    and remove that line from the text.

    Args:
        text: The answer text to process.

    Returns:
        Tuple of (tags_list, cleaned_text_without_tag_line).
    """
    lines = text.split('\n')

    # Find last non-empty line
    last_nonempty_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() != '':
            last_nonempty_idx = i
            break

    if last_nonempty_idx is None:
        return [], text

    last_line = lines[last_nonempty_idx].strip()
    if not last_line.startswith('#'):
        return [], text

    # Extract tags from '#tag1#tag2...' format
    parts = last_line.split('#')
    tag_list: list[str] = [p.strip() for p in parts if p.strip()]

    # Remove the tag line from the text (keep surrounding lines)
    cleaned_lines = lines[:last_nonempty_idx] + lines[last_nonempty_idx + 1:]
    cleaned_text = '\n'.join(cleaned_lines)

    return tag_list, cleaned_text
