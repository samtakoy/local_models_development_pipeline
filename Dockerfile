# Базовый образ: Linux (Debian) с готовым python 3.13.9
FROM python:3.13.9-slim

# Берёт программу uv из официального образа uv
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

# Рабочая папка внутри образа: дальше все пути считаются от неё
WORKDIR /app

# Копирует в образ описание проекта и код
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Ставит зависимости ровно по uv.lock, без группы dev
RUN uv sync --frozen --no-dev

# Делает команды окружения (codeteam) доступными по имени
ENV PATH="/app/.venv/bin:$PATH"

# Команда по умолчанию при запуске контейнера
CMD ["codeteam", "--help"]
