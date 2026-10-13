#!/bin/sh
# Запускает codeteam в контейнере на задаче из папки задачи с set.toml.
# Проект агентов работает в томе docker: перед прогоном копируется туда с Mac, после прогона — обратно.
# Запуск: ./run_docker.sh <папка задачи> [аргументы codeteam], например ./run_docker.sh projects/cardviewer
# Забрать результат из тома на Mac без прогона: ./run_docker.sh <папка задачи> --pull
set -e

# Папка codeteam: в ней docker-compose.yml, от неё считается путь папки задачи
cd "$(dirname "$0")"

setup_dir="$1"
if [ -z "$setup_dir" ]; then
    echo "запуск: ./run_docker.sh <папка задачи> [аргументы codeteam], например ./run_docker.sh projects/docker_check_simple"
    exit 1
fi

# Собирает образ codeteam: при первом запуске — целиком, дальше — только изменённые шаги
echo "сборка образа codeteam: первый раз — несколько минут"
docker build -q -t codeteam . > /dev/null

# Путь проекта, который видит codeteam в контейнере: считает сам codeteam по set.toml и настройкам
PROJECT_CONTAINER_DIR=$(docker run --rm -v "$PWD":/app --entrypoint python codeteam -c "
import sys
from codeteam.app.config import ConfigError, load_project_config
from codeteam.app.settings import load_settings
try:
    project = load_project_config(setup_dir = sys.argv[1], workspaces_dir = load_settings().workspaces_dir)
except ConfigError as error:
    sys.exit(f'задача не читается: {error}')
print(project.path)
" "$setup_dir")

# Тот же проект на Mac: папка codeteam в контейнере — /app; полный путь вне неё одинаков в обоих местах
case "$PROJECT_CONTAINER_DIR" in
    /app/*) PROJECT_HOST_DIR="$PWD/${PROJECT_CONTAINER_DIR#/app/}" ;;
    *) PROJECT_HOST_DIR="$PROJECT_CONTAINER_DIR" ;;
esac
mkdir -p "$PROJECT_HOST_DIR"

# Том проекта в Docker: свой у каждого проекта — имя папки и отпечаток её полного пути
project_name=$(basename "$PROJECT_HOST_DIR" | tr -c 'a-zA-Z0-9_.\n-' '_')
path_print=$(printf '%s' "$PROJECT_HOST_DIR" | shasum | cut -c1-8)
PROJECT_VOLUME="codeteam_project_${project_name}_${path_print}"
export PROJECT_CONTAINER_DIR PROJECT_HOST_DIR PROJECT_VOLUME

# Часовой пояс машины: контейнер показывает время так же, как она
TZ=$(readlink /etc/localtime | sed 's|.*zoneinfo/||')
export TZ
echo "проект агентов: $PROJECT_HOST_DIR, том: $PROJECT_VOLUME"

# Копирует результат из тома на Mac: папка становится точной копией тома; свой .venv на Mac не трогается
copy_to_host() {
    docker compose run --rm sync -a --delete --exclude /.venv /volume_project/ /host_project/
}

# --pull: только забрать результат из тома на Mac, без прогона — когда прошлый запуск не успел скопировать его сам
if [ "$2" = "--pull" ]; then
    if ! docker volume inspect "$PROJECT_VOLUME" > /dev/null 2>&1; then
        echo "тома $PROJECT_VOLUME нет: этот проект в Docker ещё не запускался"
        exit 1
    fi
    copy_to_host
    echo "результат скопирован в $PROJECT_HOST_DIR"
    exit 0
fi

# Копирует проект с Mac в том: том становится точной копией; .venv не переносится, прежний .venv тома удаляется
docker compose run --rm sync -a --delete --delete-excluded --exclude /.venv /host_project/ /volume_project/

# Прогон; Ctrl+C останавливает прогон, но не скрипт: результат всё равно копируется на Mac
status=0
trap ':' INT
docker compose run --rm codeteam "$@" || status=$?
trap - INT

copy_to_host

exit $status
