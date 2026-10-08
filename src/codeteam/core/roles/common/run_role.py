"""Запуск агента роли в пайплайне."""

from pathlib import Path

from codeteam.core.agent.role import AgentRole
from codeteam.core.agent.run_agent import run_agent
from codeteam.core.pipeline.state import PipelineConfig
from codeteam.core.roles.common.role_settings import RoleSettings


def run_role(
    *,
    cfg: PipelineConfig,
    role: RoleSettings,
    journal_name: str,
    task: str,
    input_dirs: tuple[Path, ...],
    private_dir_name: Path,
    extra_readable_dirs: tuple[Path, ...],
    extra_writable_dirs: tuple[Path, ...],
) -> Path:
    """
    Запускает агента роли и ждёт его результата.

        cfg: настройки запуска пайплайна.
        role: описание роли.
        journal_name: имя журнала агента без расширения.
        task: задача агенту.
        input_dirs: папки результатов других агентов.
        private_dir_name: путь личной папки агента внутри папки личных папок.
        extra_readable_dirs: папки чтения агента в фазе работы, кроме личной папки и папок результатов
            других агентов.
        extra_writable_dirs: папки записи агента в фазе работы, кроме черновика и файла контекста.

    Возвращает: Папку черновика агента.
    """
    agent_role = AgentRole(
        name = role.name,
        system_prompt = _load_system_prompt(path = role.system_prompt_path, fields = role.prompt_fields),
        model_name = role.model_name if role.model_name is not None else cfg.model_name,
        reasoning_level = role.reasoning_level,
        tool_names = role.tool_names,
        step_hooks = role.step_hooks,
        answer_checks = role.answer_checks,
    )

    return run_agent(
        role = agent_role,
        task = task,
        input_dirs = input_dirs,
        project_path = cfg.project_path,
        private_dir_name = private_dir_name,
        extra_readable_dirs = extra_readable_dirs,
        extra_writable_dirs = extra_writable_dirs,
        journal_path = cfg.run_dir / f"{journal_name}.md",
        settings = cfg.settings,
    )


def make_journal_name(*, journal_count: int, label: str) -> str:
    """
    Строит имя журнала следующего агента прогона.

        journal_count: число журналов агентов, уже начатых в прогоне.
        label: метка агента в имени журнала: имя роли или папка этапа с именем роли.

    Возвращает: Имя журнала без расширения, например 04_stage_100_senior.
    """
    return f"{journal_count + 1:02d}_{label}"


def _load_system_prompt(*, path: Path, fields: dict[str, str]) -> str:
    """
    Читает системный промпт роли и подставляет в него поля.

        path: файл системного промпта.
        fields: значения полей вида {имя поля} в тексте промпта.

    Возвращает: Текст системного промпта.
    """
    return path.read_text(encoding = "utf-8").strip().format(**fields)
