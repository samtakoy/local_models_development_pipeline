#!/bin/sh
# Запускает codeteam в контейнере на задаче из папки задачи с set.toml.
# Проект агентов работает в томе docker: перед прогоном копируется туда с Mac, после прогона — обратно.
# Запуск: ./run_docker.sh <папка задачи> [аргументы codeteam], например ./run_docker.sh projects/cardviewer
set -e

# Папка codeteam: в ней docker-compose.yml, от неё считается путь папки задачи
cd "$(dirname "$0")"

setup_dir="$1"

# Путь проекта, который видит codeteam в контейнере: считает сам codeteam по set.toml и настройкам
PROJECT_CONTAINER_DIR=$(docker run --rm -v "$PWD":/app --entrypoint python codeteam -c "
import sys
from codeteam.app.config import load_project_config
from codeteam.app.settings import load_settings
print(load_project_config(setup_dir = sys.argv[1], workspaces_dir = load_settings().workspaces_dir).path)
" "$setup_dir")

# Тот же проект на Mac: папка codeteam в контейнере — /app; полный путь вне неё одинаков в обоих местах
case "$PROJECT_CONTAINER_DIR" in
    /app/*) PROJECT_HOST_DIR="$PWD/${PROJECT_CONTAINER_DIR#/app/}" ;;
    *) PROJECT_HOST_DIR="$PROJECT_CONTAINER_DIR" ;;
esac
mkdir -p "$PROJECT_HOST_DIR"
export PROJECT_CONTAINER_DIR PROJECT_HOST_DIR
echo "проект агентов: $PROJECT_HOST_DIR"

# Копирует проект с Mac в том: том становится точной копией; .venv не переносится, прежний .venv тома удаляется
docker compose run --rm sync -a --delete --delete-excluded --exclude /.venv /host_project/ /volume_project/

# Прогон; Ctrl+C останавливает прогон, но не скрипт: результат всё равно копируется на Mac
status=0
trap ':' INT
docker compose run --rm codeteam "$@" || status=$?
trap - INT

# Копирует результат из тома на Mac: папка становится точной копией тома; свой .venv на Mac не трогается
docker compose run --rm sync -a --delete --exclude /.venv /volume_project/ /host_project/

exit $status
