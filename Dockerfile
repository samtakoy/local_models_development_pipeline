# Базовый образ: Linux (Debian) с готовым python 3.13.9
FROM python:3.13.9-slim

# Ставит программы, которыми пользуются агенты и codeteam
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl procps lsof git net-tools file psmisc jq sqlite3 unzip rsync \
    && rm -rf /var/lib/apt/lists/*

# Берёт Node.js из официального образа: node, npm и npx для серверов MCP
COPY --from=node:24.13.1-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24.13.1-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Ставит Chromium и его системные библиотеки той версией Playwright, что входит в Playwright MCP
RUN npx -y --package=@playwright/mcp@0.0.83 playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

# Берёт программу uv из официального образа uv
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

# Рабочая папка внутри образа: дальше все пути считаются от неё
WORKDIR /app

# Копирует в образ описание проекта и код
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Окружение python вне /app: подключённая папка проекта его не закрывает
ENV UV_PROJECT_ENVIRONMENT=/venvs/project

# Ставит зависимости ровно по uv.lock, без группы dev
RUN uv sync --frozen --no-dev

# Делает команды окружения (codeteam) доступными по имени
ENV PATH="/venvs/project/bin:$PATH"

# Программа, которую запускает контейнер
ENTRYPOINT ["codeteam"]

# Аргументы программы по умолчанию: заменяются аргументами запуска
CMD ["--help"]
