#!/bin/sh
# Запускает codeteam в контейнере: путь проекта агентов берёт из set.toml задачи.
# Проект агентов работает в томе docker: перед прогоном копируется туда с Mac, после прогона — обратно.
# Запуск: ./run_docker.sh <папка задачи> [аргументы codeteam], например ./run_docker.sh projects/cardviewer
set -e

# Папка codeteam: в ней docker-compose.yml, от неё считается путь папки задачи
cd "$(dirname "$0")"

setup_dir="$1"
PROJECT=$(sed -n 's/^project = "\(.*\)"$/\1/p' "$setup_dir/set.toml")
export PROJECT

# Копирует проект с Mac в том: том становится точной копией; .venv не переносится, прежний .venv тома удаляется
docker compose run --rm sync -a --delete --delete-excluded --exclude /.venv /host_project/ "$PROJECT/"

# Прогон; Ctrl+C останавливает прогон, но не скрипт: результат всё равно копируется на Mac
status=0
trap ':' INT
docker compose run --rm codeteam "$@" || status=$?
trap - INT

# Копирует результат из тома на Mac: папка становится точной копией тома; свой .venv на Mac не трогается
docker compose run --rm sync -a --delete --exclude /.venv "$PROJECT/" /host_project/

exit $status
