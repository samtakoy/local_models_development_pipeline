"""Tests for LibraryManager and Flask library routes."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.library import LibraryManager, SourceInfo, TopicInfo


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

EXAMPLE_CONTENT = (
    "title: Test Deck\ndesc: A test deck\n\n"
    "q: Question 1?\na:\nAnswer 1.\n#tag1\n"
)

EXAMPLE_FOLDER_2_FILES = (
    "title: Folder Card A\ndesc: Deck A\n\n"
    "q: Card in A?\na:\nAnswer A.\n"
)

EXAMPLE_FOLDER_3_FILES = (
    "title: Folder Card B\ndesc: Deck B\n\n"
    "q: Card in B?\na:\nAnswer B.\n"
)


def _make_example_file(base, name="test.txt", content=None):
    """Create a minimal valid card pack .txt file and return its path.

    Args:
        base: str or Path – the parent directory.
    """
    path = Path(base) / name
    path.write_text(content or EXAMPLE_CONTENT, encoding="utf-8")
    return str(path)


def _make_folder_with_decks(base, name="decks"):
    """Create a folder with 2-3 valid .txt card pack files.

    Returns:
        (folder_path_str, [file_paths...]).
    """
    folder = Path(base) / name
    folder.mkdir()
    file_paths = []
    for i, content in enumerate(
        [EXAMPLE_FOLDER_2_FILES, EXAMPLE_FOLDER_3_FILES], start=1
    ):
        fpath = folder / f"deck{i}.txt"
        fpath.write_text(content, encoding="utf-8")
        file_paths.append(str(fpath))
    return str(folder), file_paths


# ---------------------------------------------------------------------------
# LibraryManager unit tests
# ---------------------------------------------------------------------------

def test_create_library_default_topic():
    """Fresh library should have one default topic."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)
        data = lib.get_library_data()

        assert len(data["topics"]) == 1
        topic = data["topics"][0]
        assert topic["name"] == "По умолчанию"
        assert topic["is_default"] is True
        assert len(topic["sources"]) == 0
        assert data["default_topic_id"] == topic["id"]


def test_add_file_source():
    """Adding a valid .txt file as source should work."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id
        result = lib.add_source(file_path, topic_id)

        assert result is not None
        assert isinstance(result, SourceInfo)
        assert result.type_ == "file"
        assert len(result.decks) == 1
        assert result.decks[0]["title"] == "Test Deck"
        assert result.decks[0]["status"] == "ok"

        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        assert len(topic["sources"]) == 1


def test_add_folder_source():
    """Adding a folder with .txt files should create a folder source."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        folder_path, _ = _make_folder_with_decks(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id
        result = lib.add_source(folder_path, topic_id)

        assert result is not None
        assert result.type_ == "folder"
        assert result.deck_count == 2
        assert len(result.decks) == 2


def test_missing_file_creates_source():
    """Adding a non-existent file should create a SourceInfo with status 'missing'."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        result = lib.add_source("/nonexistent/path.txt", topic_id)
        assert result is not None
        assert isinstance(result, SourceInfo)
        assert result.type_ == "file"
        assert len(result.decks) == 1
        assert result.decks[0]["status"] == "missing"

        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        assert len(topic["sources"]) == 1


def test_add_duplicate_file():
    """Adding the same file twice should return existing SourceInfo on second call."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        result1 = lib.add_source(file_path, topic_id)
        assert result1 is not None

        result2 = lib.add_source(file_path, topic_id)
        assert result2 is not None
        assert result2.id == result1.id

        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        assert len(topic["sources"]) == 1


def test_remove_source():
    """Removing a source should delete it from the topic."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        result = lib.add_source(file_path, topic_id)
        assert result is not None
        source_id = result.id

        removed = lib.remove_source(source_id)
        assert removed is True

        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        assert len(topic["sources"]) == 0


def test_remove_nonexistent_source():
    """Removing a non-existent source should return False."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        result = lib.remove_source("nonexistent-id")
        assert result is False


def test_persistence():
    """Library should persist across restarts."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        # First instance
        lib1 = LibraryManager(lib_path)
        topic_id = lib1.default_topic_id
        lib1.add_source(file_path, topic_id)

        data1 = lib1.get_library_data()
        assert len(data1["topics"][0]["sources"]) == 1

        # Destroy and recreate
        del lib1
        lib2 = LibraryManager(lib_path)
        data2 = lib2.get_library_data()

        assert len(data2["topics"]) == 1
        assert len(data2["topics"][0]["sources"]) == 1


def test_recursive_folder_scan():
    """Folder with nested subfolders should find all .txt files."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        folder = td + "/folder"
        os.makedirs(folder)

        # Create file at root level
        root_file = os.path.join(folder, "root.txt")
        with open(root_file, "w", encoding="utf-8") as f:
            f.write(EXAMPLE_FOLDER_2_FILES)

        # Create file in subfolder
        subdir = os.path.join(folder, "sub")
        os.makedirs(subdir)
        sub_file = os.path.join(subdir, "sub.txt")
        with open(sub_file, "w", encoding="utf-8") as f:
            f.write(EXAMPLE_FOLDER_3_FILES)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id
        result = lib.add_source(folder, topic_id)

        assert result is not None
        assert result.type_ == "folder"
        assert result.deck_count == 2
        assert len(result.decks) == 2


def test_missing_path_status():
    """Deleting a file should update deck status to missing."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        # Add the source while file exists
        result = lib.add_source(file_path, topic_id)
        assert result is not None
        assert result.decks[0]["status"] == "ok"

        # Check path status
        assert lib.check_path_status(file_path) == "ok"

        # Now delete the actual file
        os.remove(file_path)
        assert lib.check_path_status(file_path) == "missing"


def test_invalid_card_pack_file():
    """An invalid card pack .txt should be handled gracefully."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")

        # Write a completely invalid file
        invalid_file = os.path.join(td, "invalid.txt")
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("this is not a valid card pack\nno structure at all\n")

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        # This should not crash
        result = lib.add_source(invalid_file, topic_id)
        # The parser won't crash but will produce an empty or weird CardPackInfo
        # We just need to ensure no exception propagates
        assert True


def test_add_source_to_nonexistent_topic():
    """Adding to a non-existent topic should return None."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        result = lib.add_source(file_path, "nonexistent-topic-id")
        assert result is None


def test_library_manager_load_from_existing():
    """Loading from existing JSON should preserve data."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")

        # First create
        lib1 = LibraryManager(lib_path)
        topic_id = lib1.default_topic_id
        source_info = SourceInfo(
            id="test-source-1",
            path="/some/path.txt",
            type_="file",
            deck_count=1,
            decks=[{"title": "Test", "status": "ok"}],
            added_at="2025-01-01T00:00:00",
        )

        # Manually add source to simulate prior state
        for topic in lib1.topics:
            if topic.id == topic_id:
                topic.sources.append(source_info)
                break
        lib1._save()

        # Load fresh
        lib2 = LibraryManager(lib_path)
        data = lib2.get_library_data()
        assert len(data["topics"]) == 1
        assert len(data["topics"][0]["sources"]) == 1
        loaded = data["topics"][0]["sources"][0]
        assert loaded["id"] == "test-source-1"


def test_source_info_serialization():
    """SourceInfo to_dict and from_dict should round-trip."""
    s = SourceInfo(
        id="s1",
        path="/a.txt",
        type_="file",
        deck_count=2,
        decks=[{"title": "D1", "status": "ok"}],
        added_at="2025-06-01T00:00:00",
    )
    d = s.to_dict()
    restored = SourceInfo.from_dict(d)

    assert restored.id == s.id
    assert restored.path == s.path
    assert restored.type_ == s.type_
    assert restored.deck_count == s.deck_count


def test_topic_info_serialization():
    """TopicInfo to_dict and from_dict should round-trip."""
    t = TopicInfo(
        id="t1",
        name="Test Topic",
        is_default=False,
        sources=[],
    )
    d = t.to_dict()
    restored = TopicInfo.from_dict(d)

    assert restored.id == t.id
    assert restored.name == t.name
    assert restored.is_default == t.is_default


# ---------------------------------------------------------------------------
# Flask integration tests
# ---------------------------------------------------------------------------

from src.app import create_app


@pytest.fixture(scope="module")
def _temp_base():
    """Create a single temp directory shared across all Flask tests."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def app(_temp_base):
    """Provide a test app with its own library path."""
    lp = os.path.join(_temp_base, "test_library.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True
    return app


def test_index_page_returns_html(_temp_base):
    """GET / should return 200 with the library page."""
    lp = os.path.join(_temp_base, "idx_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert "Card Viewer Library" in text


def test_api_sources_empty(_temp_base):
    """GET /api/sources should return empty library."""
    lp = os.path.join(_temp_base, "empty_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "topics" in data
        assert "default_topic_id" in data


def test_add_source_via_api(_temp_base):
    """POST /api/sources/add should add a source."""
    file_path = _make_example_file(_temp_base)
    lp = os.path.join(_temp_base, "add_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/api/sources")
        topic_id = resp.get_json()["topics"][0]["id"]

        resp = client.post(
            "/api/sources/add",
            json={"path": file_path, "topic_id": topic_id},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["topics"]) >= 1


def test_add_source_invalid_path(_temp_base):
    """POST /api/sources/add with nonexistent file now creates missing source."""
    lp = os.path.join(_temp_base, "inv_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/api/sources")
        topic_id = resp.get_json()["topics"][0]["id"]

        resp = client.post(
            "/api/sources/add",
            json={"path": "/nonexistent/file.txt", "topic_id": topic_id},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["topics"]) >= 1


def test_add_source_missing_fields(_temp_base):
    """POST /api/sources/add without fields should return error."""
    lp = os.path.join(_temp_base, "msf_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.post(
            "/api/sources/add",
            json={},
        )
        assert resp.status_code == 400


def test_remove_source_via_api(_temp_base):
    """DELETE /api/sources/<id> should remove the source."""
    file_path = _make_example_file(_temp_base)
    lp = os.path.join(_temp_base, "rem_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        # Get topic id
        resp = client.get("/api/sources")
        topic_id = resp.get_json()["topics"][0]["id"]

        # Add a source first
        resp = client.post(
            "/api/sources/add",
            json={"path": file_path, "topic_id": topic_id},
        )
        assert resp.status_code == 200
        add_data = resp.get_json()
        source_id = add_data["topics"][0]["sources"][0]["id"]

        # Now remove it
        resp = client.delete(f"/api/sources/{source_id}")
        assert resp.status_code == 200

        # Verify source is gone
        resp = client.get("/api/sources")
        data = resp.get_json()
        sources_found = False
        for topic in data["topics"]:
            for s in topic["sources"]:
                if s["id"] == source_id:
                    sources_found = True
        assert not sources_found


def test_remove_source_not_found(_temp_base):
    """DELETE /api/sources/<id> for non-existent source should return 404."""
    lp = os.path.join(_temp_base, "nf_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.delete("/api/sources/nonexistent-id")
        assert resp.status_code == 404


def test_add_source_with_json_body_parsing(_temp_base):
    """Adding a valid file via API should work with proper JSON body."""
    file_path = _make_example_file(_temp_base)
    lp = os.path.join(_temp_base, "json_lib.json")
    os.environ["LIBRARY_PATH"] = lp
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.get("/api/sources")
        topic_id = resp.get_json()["topics"][0]["id"]

        resp = client.post(
            "/api/sources/add",
            content_type="application/json",
            data=json.dumps({"path": file_path, "topic_id": topic_id}),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["topics"][0]["sources"][0]["type"] == "file"


# ---------------------------------------------------------------------------
# Additional unit tests for LibraryManager (Topic Management)
# ---------------------------------------------------------------------------

def test_create_topic():
    """Topic is created with correct name and is_default=False; persisted."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic = lib.create_topic("New Topic")
        assert topic.name == "New Topic"
        assert topic.is_default is False

        data = lib.get_library_data()
        assert len(data["topics"]) == 2
        non_default = [t for t in data["topics"] if not t["is_default"]][0]
        assert non_default["name"] == "New Topic"


def test_create_topic_empty_name():
    """Empty or whitespace-only name raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        with pytest.raises(ValueError, match="cannot be empty"):
            lib.create_topic("")
        with pytest.raises(ValueError):
            lib.create_topic("   ")


def test_delete_non_default_topic():
    """Non-default topic is removed and its sources moved to default."""
    with tempfile.TemporaryDirectory() as td:
        file_path = _make_example_file(td)
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        # Create a new topic
        topic = lib.create_topic("Temp Topic")
        topic_id = topic.id

        # Add source to it
        default_id = lib.default_topic_id
        src = lib.add_source(file_path, topic_id)
        assert src is not None

        # Delete the non-default topic
        lib.delete_topic(topic_id)

        data = lib.get_library_data()
        names = [t["name"] for t in data["topics"]]
        assert "Temp Topic" not in names

        # Source should be in default
        default_topic = next(t for t in data["topics"] if t["id"] == default_id)
        assert len(default_topic["sources"]) >= 1


def test_delete_default_topic_raises():
    """Deleting the default topic raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        with pytest.raises(ValueError, match="Cannot delete default"):
            lib.delete_topic(lib.default_topic_id)


def test_delete_nonexistent_topic_raises():
    """Deleting a non-existent topic raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        with pytest.raises(ValueError):
            lib.delete_topic("nonexistent-topic-uuid")


def test_move_source_between_topics():
    """Source moves from one topic to another correctly."""
    with tempfile.TemporaryDirectory() as td:
        file_path = _make_example_file(td)
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic_a = lib.create_topic("Topic A")
        topic_b = lib.create_topic("Topic B")

        # Add source to Topic A
        src = lib.add_source(file_path, topic_a.id)
        assert src is not None

        # Move from A to B
        lib.move_source(src.id, topic_b.id)

        data = lib.get_library_data()
        ta = next(t for t in data["topics"] if t["id"] == topic_a.id)
        tb = next(t for t in data["topics"] if t["id"] == topic_b.id)

        assert len(ta["sources"]) == 0
        assert len(tb["sources"]) == 1


def test_move_source_to_nonexistent_topic_raises():
    """Moving to non-existent topic raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        with pytest.raises(ValueError):
            lib.move_source("fake-source-id", "fake-topic-id")


def test_move_nonexistent_source_raises():
    """Moving non-existent source raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        with pytest.raises(ValueError):
            lib.move_source("nonexistent-source-id", lib.default_topic_id)


def test_check_all_statuses_file_ok():
    """Existing file source returns 'ok' status."""
    with tempfile.TemporaryDirectory() as td:
        file_path = _make_example_file(td)
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic_id = lib.default_topic_id
        lib.add_source(file_path, topic_id)

        statuses = lib.get_all_statuses()
        source_id = list(statuses.keys())[0]
        assert statuses[source_id] == "ok"


def test_check_all_statuses_file_missing():
    """Missing file source returns 'missing' status."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic_id = lib.default_topic_id
        lib.add_source("/nonexistent/path.txt", topic_id)

        statuses = lib.get_all_statuses()
        source_id = list(statuses.keys())[0]
        assert statuses[source_id] == "missing"


def test_check_all_statuses_empty_library():
    """Empty library returns empty dict."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        assert lib.get_all_statuses() == {}


def test_deck_has_description():
    """Parsed file deck includes description from card pack."""
    with tempfile.TemporaryDirectory() as td:
        content = (
            "title: Test Deck\ndesc: A test description\n\n"
            "q: Question?\na: Answer.\n"
        )
        file_path = _make_example_file(td, content=content)
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic_id = lib.default_topic_id
        src = lib.add_source(file_path, topic_id)
        assert src is not None
        assert len(src.decks) == 1
        assert src.decks[0]["description"] == "A test description"


def test_deck_description_empty_when_not_in_file():
    """File without desc keyword has empty description."""
    with tempfile.TemporaryDirectory() as td:
        content = "title: Test Deck\n\nq: Question?\na: Answer.\n"
        file_path = _make_example_file(td, content=content)
        lib_path = os.path.join(td, "library.json")
        lib = LibraryManager(lib_path)

        topic_id = lib.default_topic_id
        src = lib.add_source(file_path, topic_id)
        assert src is not None
        assert src.decks[0]["description"] == ""


# ---------------------------------------------------------------------------
# New tests: Status recalculation on get_library_data() and folder partial missing
# ---------------------------------------------------------------------------

def test_status_recalculation_on_get_library_data():
    """Deleting a file from disk updates the deck status to 'missing' when
    get_library_data() is called."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        file_path = _make_example_file(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        # Add source while file exists → status should be 'ok'
        result = lib.add_source(file_path, topic_id)
        assert result is not None
        assert result.decks[0]["status"] == "ok"

        # Delete the actual file from disk
        os.remove(file_path)

        # Now call get_library_data() — status should be recalculated
        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        deck = topic["sources"][0]["decks"][0]
        assert deck["status"] == "missing"


def test_folder_source_partial_missing():
    """Deleting one .txt from a folder source leaves other decks as 'ok'
    while the deleted file's deck shows 'missing'."""
    with tempfile.TemporaryDirectory() as td:
        lib_path = os.path.join(td, "library.json")
        folder_path, file_paths = _make_folder_with_decks(td)

        lib = LibraryManager(lib_path)
        topic_id = lib.default_topic_id

        # Add the folder source
        result = lib.add_source(folder_path, topic_id)
        assert result is not None
        assert len(result.decks) == 2

        # Delete the first file
        os.remove(file_paths[0])

        # Check statuses via get_library_data — folder should re-parse .txt files
        data = lib.get_library_data()
        topic = next(t for t in data["topics"] if t["id"] == topic_id)
        source = topic["sources"][0]
        assert source is not None

        # Build a title-to-status map from decks
        title_status = {d["title"]: d["status"] for d in source["decks"]}

        # The deleted file's deck should be 'missing' regardless of order
        # We know the first created file has title "Folder Card A"
        assert title_status.get("Folder Card A") == "missing"
        # The remaining file (deck2.txt) has title "Folder Card B" and should be 'ok'
        assert title_status.get("Folder Card B") == "ok"


# ---------------------------------------------------------------------------
# Additional Flask API tests (Topic Management)
# ---------------------------------------------------------------------------

def test_api_create_topic():
    """POST /api/topics/create returns 200 with topic in response."""
    with tempfile.TemporaryDirectory() as td:
        lp = os.path.join(td, "create_topic_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.post(
                "/api/topics/create",
                json={"name": "New Topic"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            topic_names = [t["name"] for t in data["topics"]]
            assert "New Topic" in topic_names


def test_api_create_topic_empty_name():
    """POST /api/topics/create with empty name returns 400."""
    with tempfile.TemporaryDirectory() as td:
        lp = os.path.join(td, "empty_name_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.post(
                "/api/topics/create",
                json={"name": ""},
            )
            assert resp.status_code == 400
            assert "error" in resp.get_json()


def test_api_delete_topic():
    """DELETE /api/topics/<id> removes the topic."""
    with tempfile.TemporaryDirectory() as td:
        lp = os.path.join(td, "del_topic_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            # Create a topic first
            resp = client.post(
                "/api/topics/create",
                json={"name": "To Delete"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            topic_id = [t for t in data["topics"] if t["name"] == "To Delete"][0]["id"]

            # Now delete it
            resp = client.delete(f"/api/topics/{topic_id}")
            assert resp.status_code == 200

            # Verify removed
            resp = client.get("/api/sources")
            data = resp.get_json()
            names = [t["name"] for t in data["topics"]]
            assert "To Delete" not in names


def test_api_delete_default_topic():
    """DELETE default topic returns 400."""
    with tempfile.TemporaryDirectory() as td:
        lp = os.path.join(td, "del_default_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            data = client.get("/api/sources").get_json()
            default_id = data["default_topic_id"]

            resp = client.delete(f"/api/topics/{default_id}")
            assert resp.status_code == 400


def test_api_move_source():
    """Move source between topics via API returns 200."""
    with tempfile.TemporaryDirectory() as td:
        file_path = _make_example_file(td)
        lp = os.path.join(td, "move_src_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            # Create two topics
            resp1 = client.post("/api/topics/create", json={"name": "Topic A"})
            resp2 = client.post("/api/topics/create", json={"name": "Topic B"})

            data = client.get("/api/sources").get_json()
            topic_a_id = [t for t in data["topics"] if t["name"] == "Topic A"][0]["id"]
            topic_b_id = [t for t in data["topics"] if t["name"] == "Topic B"][0]["id"]

            # Add source to Topic A
            resp3 = client.post(
                "/api/sources/add",
                json={"path": file_path, "topic_id": topic_a_id},
            )
            assert resp3.status_code == 200
            src_id = resp3.get_json()["topics"][1]["sources"][0]["id"]

            # Move source to Topic B
            resp4 = client.post(
                "/api/sources/move",
                json={"source_id": src_id, "target_topic_id": topic_b_id},
            )
            assert resp4.status_code == 200

            data = resp4.get_json()
            ta = [t for t in data["topics"] if t["name"] == "Topic A"][0]
            tb = [t for t in data["topics"] if t["name"] == "Topic B"][0]
            assert len(ta["sources"]) == 0
            assert len(tb["sources"]) == 1


def test_api_delete_topic_moves_sources_to_default():
    """Deleting a topic moves its sources to default via API."""
    with tempfile.TemporaryDirectory() as td:
        file_path = _make_example_file(td)
        lp = os.path.join(td, "del_src_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            # Create topic and add source
            resp = client.post("/api/topics/create", json={"name": "Temp"})
            data = resp.get_json()
            temp_id = [t for t in data["topics"] if t["name"] == "Temp"][0]["id"]

            resp2 = client.post(
                "/api/sources/add",
                json={"path": file_path, "topic_id": temp_id},
            )
            assert resp2.status_code == 200

            # Delete the topic
            resp3 = client.delete(f"/api/topics/{temp_id}")
            assert resp3.status_code == 200

            data = resp3.get_json()
            default_id = data["default_topic_id"]
            dt = next(t for t in data["topics"] if t["id"] == default_id)
            assert len(dt["sources"]) >= 1


def test_api_create_topic_whitespace_name():
    """POST /api/topics/create with whitespace-only name returns 400."""
    with tempfile.TemporaryDirectory() as td:
        lp = os.path.join(td, "whitespace_lib.json")
        os.environ["LIBRARY_PATH"] = lp

        app = create_app()
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.post(
                "/api/topics/create",
                json={"name": "   "},
            )
            assert resp.status_code == 400
