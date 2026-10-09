from dataclasses import dataclass
from pathlib import Path

from langchain_core.runnables import Runnable

from codeteam.common.shell import ShellProcesses
from codeteam.core.agent.answer_checks import AnswerCheck
from codeteam.core.agent.step_hooks import FolderHook, StepCheck
from codeteam.core.tools.files import SeenFiles


@dataclass(frozen = True)
class AgentConfig:
    system_prompt: str
    task: str
    # BaseChatModel
    chat_model: Runnable
    # имя инструмента и аргументы - вызываются на этапе инициализации агента
    warmup_calls: list[tuple[str, dict]]
    # лимит входных токенов
    history_token_limit: int
    # потолок входных токенов, после которого фаза черновика включается и во время записи ответа
    history_token_hard_limit: int
    # потолок входных токенов фазы черновика: дальше история не помещается в окно модели
    context_window_limit: int
    # предел сбросов истории агента в 0
    max_resets: int
    limit_notice: str
    reinit_notice: str
    # ответ агенту, который сдал работу с пустым черновиком
    empty_draft_notice: str
    # хуки после шага инструментов: замечания к изменённым файлам своих папок
    step_hooks: tuple[FolderHook, ...]
    # проверки после шага инструментов: замечания не к черновику, а, например, к проекту
    step_checks: tuple[StepCheck, ...]
    # проверки сдачи роли: при DONE замечания к черновику, после которых агент продолжает работу
    answer_checks: tuple[AnswerCheck, ...]

    project_dir: Path
    # путь к рабочей директории агента
    relative_private_dir: Path
    # файлы, которые видел агент; общие с файловыми инструментами, забываются при сбросе истории
    seen_files: SeenFiles
    # фоновые процессы команд агента; общие с инструментами оболочки, снимаются при уведомлении о лимите
    # и при сбросе истории
    shell_processes: ShellProcesses
