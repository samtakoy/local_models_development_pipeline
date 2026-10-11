"""
Отчёт статистики прогона: пишет файл stats_report.md в папку прогона. В конце прогона отчёт пишется сам,
скрипт нужен, чтобы пересобрать его, например для старого прогона.

Запуск:
    uv run python scripts/run_stats.py runs/<прогон>
"""

import argparse
from pathlib import Path

from codeteam.app.run_statistics import write_run_report


def main() -> None:
    """
    Пишет отчёт статистики прогона и печатает путь к нему.
    """
    parser = argparse.ArgumentParser(description = "Отчёт статистики прогона из файлов *.stats.json.")
    parser.add_argument("run_dir", help = "папка прогона, например runs/2026-10-10_22-45-01")
    arguments = parser.parse_args()

    print(write_run_report(run_dir = Path(arguments.run_dir)))


if __name__ == "__main__":
    main()
