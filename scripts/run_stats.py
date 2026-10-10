"""
Сводка статистики прогона: по каждому агенту, по роли и за прогон.

Запуск:
    uv run python scripts/run_stats.py runs/<прогон>
"""

import argparse
from pathlib import Path

from codeteam.app.run_statistics import run_report


def main() -> None:
    """
    Печатает сводку статистики прогона.
    """
    parser = argparse.ArgumentParser(description = "Сводка статистики прогона из файлов *.stats.json.")
    parser.add_argument("run_dir", help = "папка прогона, например runs/2026-10-10_22-45-01")
    arguments = parser.parse_args()

    print(run_report(run_dir = Path(arguments.run_dir)))


if __name__ == "__main__":
    main()
