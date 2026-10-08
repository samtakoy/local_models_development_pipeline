"""Общее для ролей: описание роли, наборы инструментов, запуск роли, этапы плана архитектора."""

from codeteam.core.roles.common.role_settings import DRAFT_TOOL_NAMES, PROJECT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.common.run_role import make_journal_name, run_role
from codeteam.core.roles.common.stages import ARCHITECTURE_FILE_NAME, STAGE_FILE_PATTERN, build_stage_dir_name, \
    parse_stage_number

__all__ = [
    "ARCHITECTURE_FILE_NAME",
    "DRAFT_TOOL_NAMES",
    "PROJECT_TOOL_NAMES",
    "STAGE_FILE_PATTERN",
    "RoleSettings",
    "build_stage_dir_name",
    "make_journal_name",
    "parse_stage_number",
    "run_role",
]
