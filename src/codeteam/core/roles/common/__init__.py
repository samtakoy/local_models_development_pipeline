"""Общее для ролей: описание роли, наборы инструментов, запуск роли, личные папки запусков, этапы плана
архитектора, ревью, охрана проекта от правок проверяющей роли, внешние инструменты (помощники и серверы MCP),
ошибки ролей."""

from codeteam.core.roles.common.errors import PipelineError
from codeteam.core.roles.common.external_tools import CallerContext, HelperToolBuilder, McpServerBuilder
from codeteam.core.roles.common.private_dirs import last_private_dir_name, reserve_private_dir_name, \
    role_private_dir_name
from codeteam.core.roles.common.project_guard import clean_project_check, tracked_changes_check
from codeteam.core.roles.common.review import ACCEPTED_VERDICT, REPORT_FILE_NAME, REWORK_VERDICT, \
    VERDICT_FILE_NAME, check_verdict_file, copy_reviewed_draft, make_rework, next_review_round, read_verdict, \
    rework_for, verdict_line_hook
from codeteam.core.roles.common.role_settings import DRAFT_TOOL_NAMES, PROJECT_TOOL_NAMES, RoleSettings
from codeteam.core.roles.common.run_role import make_journal_name, run_role
from codeteam.core.roles.common.stages import STAGE_FILE_PATTERN, STAGE_TASK_DIR_NAME, build_stage_dir_name, \
    parse_stage_number, read_stage_title

__all__ = [
    "ACCEPTED_VERDICT",
    "DRAFT_TOOL_NAMES",
    "PROJECT_TOOL_NAMES",
    "REWORK_VERDICT",
    "STAGE_FILE_PATTERN",
    "STAGE_TASK_DIR_NAME",
    "REPORT_FILE_NAME",
    "VERDICT_FILE_NAME",
    "CallerContext",
    "HelperToolBuilder",
    "McpServerBuilder",
    "PipelineError",
    "RoleSettings",
    "build_stage_dir_name",
    "check_verdict_file",
    "clean_project_check",
    "copy_reviewed_draft",
    "last_private_dir_name",
    "make_journal_name",
    "make_rework",
    "next_review_round",
    "parse_stage_number",
    "read_stage_title",
    "read_verdict",
    "reserve_private_dir_name",
    "rework_for",
    "role_private_dir_name",
    "run_role",
    "tracked_changes_check",
    "verdict_line_hook",
]
