"""Library manager for card deck sources.

Manages topics and their card pack sources (files or folders) with full
CRUD persistence via a JSON file.
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.parser import CardPackInfo, parse_card_pack

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_id() -> str:
    """Return a new UUID string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SourceInfo:
    """Metadata about a card pack source (file or folder)."""

    id: str
    path: str  # absolute path string
    type_: str  # "file" or "folder"
    deck_count: int
    decks: list[dict[str, Any]]  # each: {"title": ..., "status": ...}
    added_at: str  # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with 'type' key (not 'type_')."""
        return {
            "id": self.id,
            "path": self.path,
            "type": self.type_,
            "deck_count": self.deck_count,
            "decks": self.decks,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceInfo":
        return cls(
            id=data["id"],
            path=data["path"],
            type_=data["type"],
            deck_count=data["deck_count"],
            decks=data["decks"],
            added_at=data["added_at"],
        )


@dataclass
class TopicInfo:
    """A topic that groups card pack sources."""

    id: str
    name: str
    is_default: bool
    sources: list[SourceInfo]  # list of SourceInfo objects

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_default": self.is_default,
            "sources": [s.to_dict() for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TopicInfo":
        sources = [SourceInfo.from_dict(s) for s in data.get("sources", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            is_default=data.get("is_default", False),
            sources=sources,
        )


# ---------------------------------------------------------------------------
# Library Manager
# ---------------------------------------------------------------------------

class LibraryManager:
    """Manages topics and card pack sources with JSON persistence."""

    def __init__(self, library_path: str) -> None:
        self.library_path = library_path
        self.topics: list[TopicInfo] = []
        self.default_topic_id: str | None = None

        if os.path.exists(library_path):
            self._load()
        else:
            self._init_default()

        self._recalculate_all_status()
        topic_count = len(self.topics)
        source_count = sum(len(t.sources) for t in self.topics)
        logger.info(
            "Library loaded: %d topics, %d sources",
            topic_count,
            source_count,
        )

    # ---- Persistence -------------------------------------------------------

    def _load(self) -> None:
        """Load library from the JSON file."""
        with open(self.library_path, encoding="utf-8") as f:
            data = json.load(f)

        self.topics = [TopicInfo.from_dict(t) for t in data.get("topics", [])]
        self.default_topic_id = data.get("default_topic_id")
        logger.info(
            "Library loaded from %s: %d topics, default=%s",
            self.library_path,
            len(self.topics),
            self.default_topic_id,
        )

    def _init_default(self) -> None:
        """Create a fresh library with one default topic."""
        logger.info("Library initialized (fresh): no existing file found")
        topic_id = _generate_id()
        topic = TopicInfo(
            id=topic_id,
            name="По умолчанию",
            is_default=True,
            sources=[],
        )
        self.topics.append(topic)
        self.default_topic_id = topic_id
        self._save()

    def _save(self) -> None:
        """Write the library state to disk."""
        parent = os.path.dirname(self.library_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        data: dict[str, Any] = {
            "topics": [t.to_dict() for t in self.topics],
            "default_topic_id": self.default_topic_id,
        }
        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ---- Public API --------------------------------------------------------

    def add_source(self, path: str, topic_id: str) -> SourceInfo | None:
        """Add a card pack source to the given topic.

        Args:
            path: File or folder path to add as a source.
            topic_id: UUID of the target topic.

        Returns:
            The created SourceInfo on success, or None on failure.
        """
        # Validate topic exists
        topic = self._find_topic(topic_id)
        if topic is None:
            logger.warning("Topic %s not found", topic_id)
            return None

        abs_path = os.path.abspath(path)

        # Check for duplicate path in topic
        for src in topic.sources:
            if src.path == abs_path:
                logger.info("Source already exists at path: %s", abs_path)
                return src

        # Check file vs directory
        if os.path.isfile(abs_path):
            if not abs_path.lower().endswith(".txt"):
                logger.warning("Path is not a .txt file: %s", abs_path)
                return None
            return self._add_file_source(abs_path, topic)
        elif os.path.isdir(abs_path):
            return self._add_folder_source(abs_path, topic)
        else:
            logger.warning("Source path not found: %s", abs_path)
            return self._add_file_source(abs_path, topic)

    def remove_source(self, source_id: str) -> bool:
        """Remove a source from the library.

        Args:
            source_id: UUID of the source to remove.

        Returns:
            True if found and removed, False otherwise.
        """
        for topic in self.topics:
            for i, src in enumerate(topic.sources):
                if src.id == source_id:
                    topic.sources.pop(i)
                    logger.info(
                        "Removed source '%s' from topic '%s'",
                        source_id,
                        topic.name,
                    )
                    self._save()
                    self._recalculate_all_status()
                    return True
        logger.debug("Source not found: %s", source_id)
        return False

    def get_library_data(self) -> dict[str, Any]:
        """Return the full library data as a dictionary."""
        self._recalculate_all_status()
        return {
            "topics": [t.to_dict() for t in self.topics],
            "default_topic_id": self.default_topic_id,
        }

    def check_path_status(self, path: str) -> str:
        """Check if a path exists on disk.

        Returns:
            'ok' if file or directory exists, 'missing' otherwise.
        """
        if os.path.isfile(path) or os.path.isdir(path):
            return "ok"
        return "missing"

    # ---- New topic management helpers and public API ---------------------------------

    def _find_source(self, source_id: str) -> tuple[SourceInfo, TopicInfo, int, int] | None:
        """Find a source across all topics.

        Returns ``(source, topic, source_index_in_topic, topic_index)`` or ``None``.
        """
        for t_idx, topic in enumerate(self.topics):
            for s_idx, src in enumerate(topic.sources):
                if src.id == source_id:
                    return (src, topic, s_idx, t_idx)
        return None

    def create_topic(self, name: str) -> TopicInfo:
        """Create a new topic with the given name.

        Args:
            name: Display name for the topic.

        Returns:
            The created TopicInfo.

        Raises:
            ValueError: If the name is empty or whitespace-only.
        """
        if not name.strip():
            raise ValueError("Topic name cannot be empty")
        topic_id = _generate_id()
        topic = TopicInfo(
            id=topic_id,
            name=name.strip(),
            is_default=False,
            sources=[],
        )
        self.topics.append(topic)
        self._save()
        logger.info("Created topic '%s' with id %s", topic.name, topic.id)
        return topic

    def delete_topic(self, topic_id: str) -> None:
        """Delete a non-default topic and move its sources to default.

        Args:
            topic_id: UUID of the topic to delete.

        Raises:
            ValueError: If the topic is the default one or not found.
        """
        target = self._find_topic(topic_id)
        if target is None:
            raise ValueError("Topic not found")
        if target.is_default:
            raise ValueError("Cannot delete default topic")

        default_topic = self._find_topic(self.default_topic_id)
        if default_topic is None:
            raise ValueError("Default topic not found")

        for source in target.sources:
            default_topic.sources.append(source)
        target.sources.clear()
        self.topics.remove(target)
        self._save()
        logger.info("Deleted topic '%s', moved sources to default", target.name)

    def move_source(self, source_id: str, target_topic_id: str) -> None:
        """Move a source from its current topic to the target topic.

        Args:
            source_id: UUID of the source to move.
            target_topic_id: UUID of the target topic.

        Raises:
            ValueError: If either source or target topic is not found.
        """
        target = self._find_topic(target_topic_id)
        if target is None:
            raise ValueError("Target topic not found")

        result = self._find_source(source_id)
        if result is None:
            raise ValueError("Source not found")

        source, current_topic, s_idx, t_idx = result
        current_topic.sources.pop(s_idx)
        target.sources.append(source)
        self._save()
        logger.info(
            "Moved source %s from topic '%s' to topic '%s'",
            source_id,
            current_topic.name,
            target.name,
        )

    def get_all_statuses(self) -> dict[str, str]:
        """Return status of every source in the library.

        Returns:
            Dict mapping source_id to "ok" or "missing".
        """
        statuses: dict[str, str] = {}
        for topic in self.topics:
            for source in topic.sources:
                statuses[source.id] = self.check_path_status(source.path)
        return statuses

    # ---- Public: get source by ID ------------------------------------------

    def get_source(self, source_id: str) -> SourceInfo | None:
        """Return a source by its ID across all topics, or None."""
        result = self._find_source(source_id)
        if result is None:
            return None
        return result[0]

    # ---- Internal helpers --------------------------------------------------

    def _find_topic(self, topic_id: str) -> TopicInfo | None:
        for topic in self.topics:
            if topic.id == topic_id:
                return topic
        return None

    def _add_file_source(self, abs_path: str, topic: TopicInfo) -> SourceInfo | None:
        """Add a single .txt file as a source."""
        if not os.path.isfile(abs_path):
            logger.info("Added missing file source '%s'", abs_path)
            deck_info: dict[str, Any] = {
                "title": os.path.basename(abs_path),
                "status": "missing",
                "description": "",
            }
            source = SourceInfo(
                id=_generate_id(),
                path=abs_path,
                type_="file",
                deck_count=1,
                decks=[deck_info],
                added_at="",
            )
            topic.sources.append(source)
            self._save()
            return source

        try:
            info = parse_card_pack(abs_path)
        except Exception as exc:
            logger.warning(
                "Failed to parse card pack at '%s': %s", abs_path, exc
            )
            deck_info: dict[str, Any] = {
                "title": os.path.basename(abs_path),
                "status": "ok",
                "description": "",
            }
        else:
            deck_info = {
                "title": info.title if info.title else os.path.basename(abs_path),
                "status": "ok",
                "description": info.description if info.description else "",
            }

        source = SourceInfo(
            id=_generate_id(),
            path=abs_path,
            type_="file",
            deck_count=1,
            decks=[deck_info],
            added_at="",
        )
        topic.sources.append(source)
        self._save()
        logger.info(
            "Added source '%s' as file in topic '%s'", abs_path, topic.name
        )
        return source

    def _add_folder_source(self, abs_path: str, topic: TopicInfo) -> SourceInfo | None:
        """Add a folder containing .txt card pack files as a source."""
        txt_files = list(Path(abs_path).rglob("*.txt"))

        if len(txt_files) == 0:
            logger.warning(
                "No .txt files found in folder '%s'", abs_path
            )
            return None

        decks: list[dict[str, Any]] = []
        for txt_file in txt_files:
            try:
                info = parse_card_pack(str(txt_file))
                decks.append({
                    "title": info.title if info.title else txt_file.name,
                    "status": "ok",
                    "description": info.description if info.description else "",
                })
            except Exception as exc:
                logger.warning(
                    "Failed to parse card pack at '%s': %s",
                    txt_file,
                    exc,
                )
                continue

        source = SourceInfo(
            id=_generate_id(),
            path=abs_path,
            type_="folder",
            deck_count=len(decks),
            decks=decks,
            added_at="",
        )
        topic.sources.append(source)
        self._save()
        logger.info(
            "Added source '%s' as folder with %d decks in topic '%s'",
            abs_path,
            len(decks),
            topic.name,
        )
        return source

    def _recalculate_all_status(self) -> None:
        """Update deck statuses (ok / missing) for all sources."""
        for topic in self.topics:
            for source in topic.sources:
                if source.type_ == "file":
                    status = self.check_path_status(source.path)
                    for d in source.decks:
                        d["status"] = status
                        logger.info("Status updated: %s -> %s", d.get("title", "unknown"), status)
                elif source.type_ == "folder":
                    # Build set of valid titles by parsing all .txt files in folder
                    matched_titles: dict[str, bool] = {}
                    for txt_file in Path(source.path).rglob("*.txt"):
                        try:
                            info = parse_card_pack(str(txt_file))
                            if info.title:
                                matched_titles[info.title.lower()] = True
                        except Exception:
                            pass  # Skip unparseable files

                    for d in source.decks:
                        title_lower = d.get("title", "").lower()
                        if title_lower in matched_titles:
                            d["status"] = "ok"
                        else:
                            d["status"] = "missing"
                        logger.info("Status updated: %s -> %s", d.get("title", "unknown"), d["status"])
        self._save()
