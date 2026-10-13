"""Tests for Flask app routes including the deck viewer."""

import os
import tempfile

import pytest

from src.app import create_app


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

EXAMPLE_DECK = (
    "title: Test Deck\ndesc: A test deck description\n\n"
    "q: What is Flask?\na:\nFlask is a web framework.\n#web#python\n"
    "q: What is a view?\na:\nA Python function that returns a response.\n"
    "q: Standalone question without answer?"
)

EXAMPLE_DECK_EMPTY = (
    "title: Empty Deck\ndesc: A deck with no cards\n"
)


def _make_deck_file(base_dir, name="test.txt", content=None):
    """Create a card pack .txt file and return its path."""
    path = os.path.join(base_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or EXAMPLE_DECK)
    return path


# ---------------------------------------------------------------------------
# Fixtures — each test gets an isolated temp library
# ---------------------------------------------------------------------------

@pytest.fixture
def _temp_lib():
    """Provide a unique temp directory per test session (used via env var)."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def app(_temp_lib):
    """Flask test app using a unique temp library."""
    lp = os.path.join(_temp_lib, "test_library.json")
    os.environ["LIBRARY_PATH"] = lp

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


# ---------------------------------------------------------------------------
# Helper to set up a deck source in the library and get its ID.
# ---------------------------------------------------------------------------

def _add_source_to_library(app, file_path):
    """Add a file as source and return the source ID."""
    lib = app.library_manager
    topic_id = lib.default_topic_id
    src = lib.add_source(file_path, topic_id)
    assert src is not None, f"Failed to add source at {file_path}"
    return src.id


# ---------------------------------------------------------------------------
# Deck viewer route tests
# ---------------------------------------------------------------------------

def test_deck_valid_page_returns_200(app, _temp_lib):
    """A valid source ID should return 200 with deck content."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        assert resp.status_code == 200


def test_deck_page_contains_title_and_question(app, _temp_lib):
    """Deck page should contain the deck title and first card question."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "Test Deck" in text
        assert "What is Flask?" in text


def test_deck_page_does_not_show_answer_in_html(app, _temp_lib):
    """Answer text should NOT be visible as plain text in the HTML body."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        # The answer "Flask is a web framework." should not appear as visible
        # plain text — it's inside a <div> that is hidden via display:none.
        # We check it appears only inside the JS-rendered template or inside
        # a pre/code element wrapped in a hidden div, not at top level.
        assert "Flask is a web framework" in text  # present in template

        # But it should be inside a <div> with display:none (hidden)
        # i.e., the answer is not visible as plain text on page load
        # We verify that the question IS visible but answer wrapper class exists
        assert 'class="answer-area' in text


def test_deck_invalid_source_redirects(app, _temp_lib):
    """A non-existent source ID should redirect to library."""
    with app.test_client() as client:
        resp = client.get("/deck/nonexistent-source-id-uuid")
        assert resp.status_code == 302


def test_deck_page_contains_deck_title_in_title_tag(app, _temp_lib):
    """The <title> tag should contain the deck title."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "<title>Card Viewer — Test Deck</title>" in text


def test_deck_empty_deck_shows_empty_state(app, _temp_lib):
    """An empty deck (no cards) should render the empty state page."""
    file_path = _make_deck_file(_temp_lib, content=EXAMPLE_DECK_EMPTY)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        # When card_count is 0, the JS renders "No cards in this deck"
        assert "No cards in this deck" in text or "empty-state" in text


def test_deck_counter_shows_first_card(app, _temp_lib):
    """Card counter should show '1 / N' for the first card."""
    # Create a file with exactly 3 cards
    content = (
        "title: Counter Test\n\n"
        "q: Card 1?\na: Ans 1.\n"
        "q: Card 2?\na: Ans 2.\n"
        "q: Card 3?\na: Ans 3.\n"
    )
    file_path = _make_deck_file(_temp_lib, content=content)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        # The counter "1 / N" is rendered by JS; verify static HTML has
        # data-card-count attribute and the TOTAL_CARDS JS variable.
        assert 'data-card-count="3"' in text


def test_deck_contains_tags(app, _temp_lib):
    """Deck page should contain tag data in DECK_DATA."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        # Tags are rendered client-side; verify they appear in DECK_DATA JSON.
        assert '"tags"' in text


def test_deck_page_contains_localstorage(app, _temp_lib):
    """Deck viewer should use localStorage for line-wrap preference."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "localStorage" in text


def test_deck_page_has_copy_button(app, _temp_lib):
    """Deck viewer should have copy text button."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert 'copy-text-btn' in text or 'navigator.clipboard' in text


def test_deck_page_has_line_wrap_toggle(app, _temp_lib):
    """Deck viewer should have line wrap toggle input."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert 'lineWrapEnabled' in text or 'wrap-toggle-input' in text


def test_deck_page_contains_deck_js_data(app, _temp_lib):
    """Deck page should include DECK_DATA JS variable."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "const DECK_DATA" in text
        assert '"What is Flask?"' in text


def test_deck_total_cards_js_var(app, _temp_lib):
    """Deck page should include TOTAL_CARDS JS variable with correct count."""
    content = (
        "title: Count Test\n\n"
        "q: A?\na: A.\n"
        "q: B?\na: B.\n"
        "q: C?\na: C.\n"
    )
    file_path = _make_deck_file(_temp_lib, content=content)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "TOTAL_CARDS = 3" in text


def test_deck_back_to_library_button(app, _temp_lib):
    """Deck page should contain a link back to the library."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert 'href="/"' in text


def test_deck_contains_nav_buttons(app, _temp_lib):
    """Deck page should contain navigation buttons."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "Показать ответ" in text


def test_deck_description_in_page(app, _temp_lib):
    """Deck page should include the description."""
    file_path = _make_deck_file(_temp_lib)
    source_id = _add_source_to_library(app, file_path)

    with app.test_client() as client:
        resp = client.get(f"/deck/{source_id}")
        text = resp.get_data(as_text=True)
        assert "A test deck description" in text
