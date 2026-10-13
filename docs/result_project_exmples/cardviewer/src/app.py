"""Flask web application for viewing flashcard decks."""

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

from src.library import LibraryManager

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        Configured Flask app instance.
    """
    _base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(
        __name__,
        template_folder=os.path.join(_base_dir, 'templates'),
        static_folder=os.path.join(_base_dir, 'static'),
    )

    # Instantiate library manager
    library_path = os.environ.get("LIBRARY_PATH", "data/library.json")
    library = LibraryManager(library_path)
    app.library_manager = library  # attach for testability

    @app.route("/")
    def index():
        return render_template("library.html", library=library.get_library_data())

    @app.route("/api/sources")
    def api_sources():
        return jsonify(library.get_library_data())

    @app.route("/api/sources/add", methods=["POST"])
    def api_add_source():
        try:
            data = request.get_json(force=True)
            if data is None:
                return jsonify({"error": "Invalid JSON body"}), 400

            path = data.get("path")
            topic_id = data.get("topic_id")

            if not path or not topic_id:
                return jsonify({"error": "Missing 'path' or 'topic_id'"}), 400

            result = library.add_source(path, topic_id)
            if result is None:
                return jsonify(
                    {"error": f"Failed to add source at path: {path}"}
                ), 400

            return jsonify(library.get_library_data())
        except Exception as exc:
            logger.error("Error adding source: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/sources/<source_id>", methods=["DELETE"])
    def api_remove_source(source_id):
        try:
            success = library.remove_source(source_id)
            if not success:
                return jsonify({"error": f"Source not found: {source_id}"}), 404
            return jsonify(library.get_library_data())
        except Exception as exc:
            logger.error("Error removing source: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/sources/move", methods=["POST"])
    def api_move_source():
        try:
            data = request.get_json(force=True)
            if data is None or not data.get("source_id") or not data.get("target_topic_id"):
                return jsonify({"error": "Missing 'source_id' or 'target_topic_id'"}), 400

            source_id = data["source_id"]
            target_topic_id = data["target_topic_id"]

            library.move_source(source_id, target_topic_id)
            logger.info("Moved source %s", source_id)
            return jsonify(library.get_library_data())
        except ValueError as exc:
            logger.warning("Move source error: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("Error moving source: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/topics/create", methods=["POST"])
    def api_create_topic():
        try:
            data = request.get_json(force=True, silent=True)
            if data is None or not data.get("name"):
                return jsonify({"error": "Missing 'name' parameter"}), 400

            name = data["name"].strip()
            if not name:
                return jsonify({"error": "Topic name cannot be empty"}), 400

            library.create_topic(name)
            logger.info("Created topic '%s'", name)
            return jsonify(library.get_library_data())
        except ValueError as exc:
            logger.warning("Create topic error: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("Error creating topic: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/topics/<topic_id>", methods=["DELETE"])
    def api_delete_topic(topic_id):
        try:
            library.delete_topic(topic_id)
            logger.info("Deleted topic '%s'", topic_id)
            return jsonify(library.get_library_data())
        except ValueError as exc:
            logger.warning("Delete topic error: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("Error deleting topic: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/deck/<source_id>")
    def deck_viewer(source_id):
        """Serve the deck viewer page for a given source ID."""
        try:
            src = library.get_source(source_id)
            if src is None:
                logger.warning("Source not found for ID: %s", source_id)
                return redirect("/")

            # Determine file path to parse
            if src.type_ == "file":
                file_path = src.path
            elif src.type_ == "folder":
                txt_files = list(Path(src.path).rglob("*.txt"))
                if len(txt_files) == 0:
                    logger.warning(
                        "No .txt files found in folder source: %s",
                        src.id,
                    )
                    return redirect("/")
                file_path = str(txt_files[0])
            else:
                logger.warning("Unknown source type: %s", src.type_)
                return redirect("/")

            # Parse the card pack
            from src.parser import parse_card_pack

            info = parse_card_pack(file_path)

            # Build cards list
            cards = []
            for card in info.cards:
                cards.append({
                    "question": card.question,
                    "answer": card.answer if card.answer is not None else "",
                    "tags": card.tags if card.tags else [],
                })

            title = info.title if info.title else os.path.basename(file_path)
            description = info.description if info.description else ""

            logger.info(
                "Opened deck '%s' (%d cards) from source %s",
                title,
                len(cards),
                source_id,
            )

            return render_template(
                "deck_view.html",
                title=title,
                description=description,
                cards=cards,
                card_count=len(cards),
            )

        except Exception as exc:
            logger.error("Error opening deck for source %s: %s", source_id, exc)
            return redirect("/")

    @app.route("/api/decks")
    def list_decks():
        return jsonify({"decks": []})

    @app.route("/api/decks/<deck_id>/cards")
    def list_cards(deck_id):
        return jsonify({"cards": []})

    logger.info("Flask app created successfully")
    return app


def main():
    """Entry point: read environment config and start the server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/app.log", encoding="utf-8"),
        ],
    )

    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8050"))
    library_path = os.environ.get("LIBRARY_PATH", "data/library.json")

    logger.info(
        "Starting server on %s:%d with library at %s", host, port, library_path
    )

    app = create_app()
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
