# Card Viewer

A local Flask web application for viewing and studying flashcard decks stored in plain-text `.txt` files.
Add your decks, organize them into topics, and study with intuitive navigation — all running locally on your machine.

## Start

```bash
uv run python -m src.app
```

The server starts by default on `http://127.0.0.1:8050`.
Open your browser and start studying!

## Environment Variables

| Variable       | Default            | Description                                      |
|----------------|--------------------|--------------------------------------------------|
| `APP_HOST`     | `127.0.0.1`        | Bind address for the web server                  |
| `APP_PORT`     | `8050`             | Port for the web server                          |
| `LIBRARY_PATH` | `data/library.json`| Path to the deck library JSON file               |

Example:

```bash
APP_HOST=0.0.0.0 APP_PORT=9000 uv run python -m src.app
```

## Features

### Library Management
- Add card deck sources from `.txt` files or folders containing multiple decks
- Organize sources into named topics; move sources between topics
- Delete topics and sources; missing files are detected and marked
- Library persists between restarts in a JSON file

### Card Viewer
- Study cards one at a time with question → answer workflow
- Navigate: **←** (previous), **→ / Space** (show answer / next card)
- Show/hide answers, jump to any card by number
- Copy card text to clipboard with one click
- Toggle code line-wrap; preference saved in browser localStorage
- Beautiful dark theme with blue accents and smooth animations

### Design
- Dark theme with accent blue elements
- Smooth fade-in and slide animations for cards
- Responsive layout for different screen sizes

## Project Structure

```
src/
  app.py       # Flask application entry point
  parser.py    # Card pack file parser
  library.py   # Library manager (topics, sources, persistence)
tests/
  test_parser.py   # Parser unit tests
  test_library.py  # Library manager tests
  test_app.py      # Flask route tests
docs/
  card_pack_example.txt   # Example card pack file
  card_pack_specs.md      # Card pack format specification
data/                      # Application data (deck library JSON)
logs/                      # Application logs
```

## License

Local use only.