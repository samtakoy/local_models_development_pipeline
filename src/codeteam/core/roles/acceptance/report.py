"""Отчёт итоговой приёмки в папке прогона: вердикт и план доработки одним файлом."""

from pathlib import Path

# Файл в папке прогона: вердикт и план доработки последней итоговой приёмки.
ACCEPTANCE_REPORT_FILE_NAME = "acceptance_report.md"


def write_acceptance_report(*, run_dir: Path, acceptance_dir: Path) -> Path:
    """
    Пишет в папку прогона вердикт и план доработки последней итоговой приёмки одним файлом.

        run_dir: папка прогона.
        acceptance_dir: папка черновика итоговой приёмки: вердикт и план доработки.

    Возвращает: Файл ACCEPTANCE_REPORT_FILE_NAME в папке прогона.
    """
    report = "\n\n".join(
        path.read_text(encoding = "utf-8", errors = "replace").strip() for path in sorted(acceptance_dir.glob("*.md"))
    )
    report_file = run_dir / ACCEPTANCE_REPORT_FILE_NAME
    report_file.write_text(report + "\n", encoding = "utf-8")

    return report_file
