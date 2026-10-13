#!/bin/sh
# Запускает codeteam в контейнере: путь проекта агентов берёт из set.toml задачи.
# Запуск: ./run_docker.sh <папка задачи> [аргументы codeteam], например ./run_docker.sh projects/cardviewer
set -e

# Папка codeteam: в ней docker-compose.yml, от неё считается путь папки задачи
cd "$(dirname "$0")"

setup_dir="$1"
PROJECT=$(sed -n 's/^project = "\(.*\)"$/\1/p' "$setup_dir/set.toml")
export PROJECT

docker compose run --rm codeteam "$@"
