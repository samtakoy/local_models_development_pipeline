"""Тесты хука личной папки: какой файл получает замечание и какой правильный путь в нём назван."""

from pathlib import Path

from codeteam.core.agent.step_hooks import StepHook, private_file_hook

# Личная папка агента в тестах относительно папки проекта.
PRIVATE_DIR = Path(".ct-work/stage_030/browser_checker_r5")

# Файл ответа роли в тестах.
ANSWER_FILE_NAME = "000_observations.md"

# Путь файла ответа в черновике, как его видит агент.
SHOWN_ANSWER_PATH = f"{PRIVATE_DIR.as_posix()}/draft/{ANSWER_FILE_NAME}"

# Путь файла контекста, как его видит агент.
SHOWN_CONTEXT_PATH = f"{PRIVATE_DIR.as_posix()}/context.md"


def _hook(*, project_dir: Path, only_answer_files: bool) -> StepHook:
    """
    Собирает хук личной папки роли с одним файлом ответа.

        project_dir: папка проекта.
        only_answer_files: в черновике роли разрешены только файлы ответа.

    Возвращает: Хук после шага.
    """
    return private_file_hook(
        project_dir = project_dir,
        private_dir = project_dir / PRIVATE_DIR,
        answer_file_names = (ANSWER_FILE_NAME,),
        only_answer_files = only_answer_files,
    )


def _remark(*, project_dir: Path, only_answer_files: bool, file_path: str) -> str | None:
    """
    Запускает хук на файле личной папки.

        project_dir: папка проекта.
        only_answer_files: в черновике роли разрешены только файлы ответа.
        file_path: путь файла относительно личной папки.

    Возвращает: Замечание хука или None.
    """
    hook = _hook(project_dir = project_dir, only_answer_files = only_answer_files)

    return hook(project_dir / PRIVATE_DIR / file_path, "# Заголовок")


def test_files_on_their_places_give_no_remark(tmp_path: Path) -> None:
    """
    Файл контекста и файл ответа на своих местах замечаний не получают.
    """
    for file_path in ("context.md", f"draft/{ANSWER_FILE_NAME}"):
        assert _remark(project_dir = tmp_path, only_answer_files = True, file_path = file_path) is None


def test_misplaced_context_file_gets_context_path(tmp_path: Path) -> None:
    """
    Файл контекста не на своём месте на любой глубине личной папки — в замечании путь файла контекста.
    """
    for file_path in ("draft/context.md", "helpers/context.md", "helpers/deep/context.md"):
        remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = file_path)

        assert remark is not None and SHOWN_CONTEXT_PATH in remark


def test_context_like_file_gets_context_path(tmp_path: Path) -> None:
    """
    Файл с номером перед именем файла контекста в черновике и в другой папке — в замечании путь файла контекста.
    """
    for file_path in ("draft/000_context.md", "helpers/100_context.md"):
        remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = file_path)

        assert remark is not None and SHOWN_CONTEXT_PATH in remark


def test_misplaced_answer_file_gets_answer_path(tmp_path: Path) -> None:
    """
    Файл ответа вне черновика и в подпапке черновика — в замечании его путь в черновике.
    """
    for file_path in (ANSWER_FILE_NAME, f"helpers/{ANSWER_FILE_NAME}", f"helpers/draft/{ANSWER_FILE_NAME}",
                      f"draft/sub/{ANSWER_FILE_NAME}"):
        remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = file_path)

        assert remark is not None and SHOWN_ANSWER_PATH in remark


def test_answer_topic_with_other_number_gets_answer_path(tmp_path: Path) -> None:
    """
    Раздел с темой файла ответа под другим номером, в черновике и вне его, — в замечании путь файла ответа;
    у роли без ограничения на файлы черновика тоже.
    """
    for file_path in ("draft/100_observations.md", "draft/00_observations.md", "helpers/200_observations.md"):
        remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = file_path)

        assert remark is not None and SHOWN_ANSWER_PATH in remark


def test_other_draft_file_gets_answer_path_when_only_answer_files(tmp_path: Path) -> None:
    """
    В черновике роли только с файлами ответа другой раздел получает замечание с путём файла ответа;
    у роли без такого ограничения тот же раздел замечаний не получает.
    """
    restricted_remark = _remark(project_dir = tmp_path, only_answer_files = True, file_path = "draft/000_deck_test.md")
    free_remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = "draft/000_deck_test.md")

    assert restricted_remark is not None and SHOWN_ANSWER_PATH in restricted_remark
    assert free_remark is None


def test_draft_file_with_wrong_name_gets_remark(tmp_path: Path) -> None:
    """
    Файл черновика с именем не по правилу раздела получает замечание.
    """
    assert _remark(project_dir = tmp_path, only_answer_files = False, file_path = "draft/notes.txt") is not None


def test_stray_file_gets_draft_and_context_paths(tmp_path: Path) -> None:
    """
    Прочий файл личной папки — в замечании полные пути черновика и файла контекста.
    """
    remark = _remark(project_dir = tmp_path, only_answer_files = False, file_path = "notes.txt")

    assert remark is not None
    assert f"{PRIVATE_DIR.as_posix()}/draft/" in remark
    assert SHOWN_CONTEXT_PATH in remark
