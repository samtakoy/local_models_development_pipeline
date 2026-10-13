"""Tests for card pack parser."""

import os
import tempfile

from src.parser import (
    Card,
    CardPackInfo,
    parse_card_pack,
    parse_card_pack_from_string,
)


def _example_path():
    return os.path.join(os.path.dirname(__file__), '..', 'docs', 'card_pack_example.txt')


# ─── 1. test_parse_example_file ─────────────────────────────────────────────

def test_parse_example_file():
    """Parse the real example file and verify key fields."""
    info = parse_card_pack(_example_path())

    # Header fields
    assert (
        info.title
        == "StyleCLIP: Text-Driven Manipulation of StyleGAN Imagery"
    )
    assert "15-06-2026 13:41:45" in info.date
    assert "Обучающие карточки по статье StyleCLIP" in info.description

    # Card count — the example has 16 cards (q: blocks)
    assert len(info.cards) == 16


def test_parse_example_first_card():
    """First card should have expected question and answer content."""
    info = parse_card_pack(_example_path())
    first = info.cards[0]

    assert "StyleCLIP" in first.question
    assert "TL;DR" in first.answer
    assert first.tags == ["styleclip", "обзор"]


def test_parse_example_tagged_cards():
    """Cards with tag lines should have extracted tags."""
    info = parse_card_pack(_example_path())

    # Find a card with known tags, e.g. terms card → ["термины"]
    terms_card = next(
        (c for c in info.cards if "Основные термины StyleCLIP" in c.question),
        None,
    )
    assert terms_card is not None
    assert terms_card.tags == ["термины"]


# ─── 2. test_parse_empty_file ──────────────────────────────────────────────

def test_parse_empty_file(tmp_path):
    """Empty file returns empty CardPackInfo."""
    path = tmp_path / "empty.txt"
    path.write_text("")

    info = parse_card_pack(str(path))
    assert info.title == ""
    assert info.description == ""
    assert info.date is None
    assert info.cards == []


def test_parse_empty_string():
    """Empty string also returns empty CardPackInfo."""
    info = parse_card_pack_from_string("")
    assert info.title == ""
    assert info.description == ""
    assert info.date is None
    assert info.cards == []


# ─── 3. test_parse_no_cards ────────────────────────────────────────────────

def test_parse_no_cards(tmp_path):
    """Header-only file produces no cards."""
    content = "title: Test Deck\ndesc: A test description\n"
    path = tmp_path / "no_cards.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    assert info.title == "Test Deck"
    assert "A test description" in info.description
    assert info.cards == []


# ─── 4. test_parse_card_without_answer ─────────────────────────────────────

def test_parse_card_without_answer(tmp_path):
    """Card with q: but no a: should have answer=None."""
    content = "title: Test\nq: What is the question?\n"
    path = tmp_path / "no_answer.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    assert len(info.cards) == 1
    card = info.cards[0]
    assert "What is the question?" in card.question
    assert card.answer is None


def test_parse_card_without_answer_string():
    """Same as above but via string parser."""
    content = "q: Standalone question?\n"
    info = parse_card_pack_from_string(content)
    assert len(info.cards) == 1
    assert info.cards[0].answer is None


# ─── 5. test_parse_tags_extraction ─────────────────────────────────────────

def test_parse_tags_extraction(tmp_path):
    """Tags extracted from last non-empty line of answer."""
    content = (
        "title: Test\nq: Question?\na:\nAnswer text here.\n#tag1#tag2#tag3\n"
    )
    path = tmp_path / "tags.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    card = info.cards[0]
    assert card.tags == ["tag1", "tag2", "tag3"]
    # Tag line should be removed from answer body
    assert "#tag1#tag2#tag3" not in card.answer


def test_parse_tags_extraction_string():
    """Same via string parser."""
    content = "q: Q?\na:\nSome answer.\n#foo#bar\n"
    info = parse_card_pack_from_string(content)
    assert info.cards[0].tags == ["foo", "bar"]
    assert "#foo#bar" not in info.cards[0].answer


# ─── 6. test_parse_multiple_keywords_first_wins ─────────────────────────────

def test_parse_duplicate_keywords_first_wins(tmp_path):
    """Duplicate keywords: first value wins."""
    content = (
        "title: First Title\n"
        "title: Second Title\n"
        "desc: First Desc\n"
        "desc: Second Desc\n"
        "\nq: Card?\na: Answer.\n"
    )
    path = tmp_path / "dup.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    assert info.title == "First Title"
    # First desc wins
    assert "First Desc" in info.description


def test_parse_duplicate_keywords_first_wins_string():
    """Same via string parser."""
    content = "title: Alpha\ntitle: Beta\nq: Q?\na: A.\n"
    info = parse_card_pack_from_string(content)
    assert info.title == "Alpha"


# ─── 7. test_parse_crlf_line_endings ───────────────────────────────────────

def test_parse_crlf_line_endings(tmp_path):
    """CRLF line endings produce same output as LF."""
    content = (
        "title: CRLF Deck\r\ndesc: A description.\r\n\r\n"
        "q: Card 1?\r\na:\r\nAnswer 1.\r\n#t1\r\n"
    )
    path = tmp_path / "crlf.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    assert info.title == "CRLF Deck"
    assert len(info.cards) == 1
    assert info.cards[0].tags == ["t1"]


def test_parse_crlf_matches_lf(tmp_path):
    """CRLF content should equal equivalent LF content."""
    lf_content = (
        "title: CRLF Deck\ndesc: A description.\n\n"
        "q: Card 1?\na:\nAnswer 1.\n#t1\n"
    )

    crlf_path = tmp_path / "crlf.txt"
    crlf_path.write_text(lf_content.replace("\n", "\r\n"))

    lf_info = parse_card_pack_from_string(lf_content)
    crlf_info = parse_card_pack(str(crlf_path))

    assert lf_info.title == crlf_info.title
    assert lf_info.date == crlf_info.date
    assert len(lf_info.cards) == len(crlf_info.cards)


# ─── 8. test_empty_answer_no_tags ──────────────────────────────────────────

def test_empty_answer_no_tags(tmp_path):
    """Card with empty answer (just 'a:' and nothing else)."""
    content = "q: Question?\na:\n"
    path = tmp_path / "empty_answer.txt"
    path.write_text(content)

    info = parse_card_pack(str(path))
    card = info.cards[0]
    assert card.answer is None or card.answer.strip() == ""
    assert card.tags == []


def test_empty_answer_no_tags_string():
    """Same via string parser."""
    content = "q: Q?\na:\n"
    info = parse_card_pack_from_string(content)
    card = info.cards[0]
    assert card.answer is None or card.answer.strip() == ""
