"""Инструмент describe_picture: смотрящая модель описывает картинку из проекта для разработчиков."""

import base64
import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages.content import create_image_block, create_text_block
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.llm import GenerationMode, OllamaConfig, ReasoningLevel, build_chat_model
from codeteam.core.roles.common import CallerContext
from codeteam.core.roles.picture_viewer.prompts import (
    FOCUS_NOT_GIVEN,
    DESCRIBE_PICTURE_DESCRIPTION,
    DESCRIBE_PICTURE_FILE_PATH_DESCRIPTION,
    DESCRIBE_PICTURE_FOCUS_DESCRIPTION,
    NOT_PICTURE_ERROR,
    PICTURE_DESCRIPTION_PROMPT,
    PICTURE_NOT_FOUND_ERROR,
    PICTURE_OUTSIDE_PROJECT_ERROR,
    PICTURE_REQUEST,
)

logger = logging.getLogger(__name__)

# Имя инструмента описания картинки.
DESCRIBE_PICTURE_TOOL_NAME = "describe_picture"

# Тип содержимого картинки по расширению файла.
PICTURE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class LookAtPictureArguments(BaseModel):
    """
    Аргументы describe_picture.
    """

    file_path: str = Field(description = DESCRIBE_PICTURE_FILE_PATH_DESCRIPTION)
    focus: str | None = Field(default = None, description = DESCRIBE_PICTURE_FOCUS_DESCRIPTION)


def build_describe_picture_tool(caller_context: CallerContext) -> BaseTool | None:
    """
    Собирает инструмент describe_picture для вызывающего агента.

        caller_context: агент, который будет смотреть картинки.

    Возвращает: Инструмент describe_picture; None, если смотрящая модель не задана в настройках.
    """
    settings = caller_context.cfg.settings
    if settings.vision_model is None:
        return None

    project_dir = Path(caller_context.cfg.project_path).resolve()
    chat_model = build_chat_model(
        config = OllamaConfig(
            base_url = settings.ollama_base_url,
            model = settings.vision_model,
            context_window = settings.vision_ctx_window,
        ),
        generation_mode = GenerationMode.THINKING,
        reasoning_level = ReasoningLevel.NONE,
    )

    def describe_picture(*, file_path: str, focus: str | None = None) -> str:
        """
        Описывает картинку из проекта.

            file_path: путь картинки от агента, относительно папки проекта.
            focus: на что обратить внимание; None - не указано.

        Возвращает: Описание картинки от смотрящей модели. Ошибку для агента поднимает ToolException.
        """
        picture_path = find_picture(project_dir = project_dir, file_path = file_path)
        encoded = base64.b64encode(picture_path.read_bytes()).decode("ascii")
        media_type = PICTURE_MEDIA_TYPES[picture_path.suffix.lower()]
        started = time.monotonic()
        response = chat_model.invoke([
            SystemMessage(content = PICTURE_DESCRIPTION_PROMPT),
            HumanMessage(content = [
                create_text_block(text = PICTURE_REQUEST.format(focus = focus or FOCUS_NOT_GIVEN)),
                create_image_block(base64 = encoded, mime_type = media_type),
            ]),
        ])
        logger.info(f"[{DESCRIBE_PICTURE_TOOL_NAME}] {file_path}: {time.monotonic() - started:.1f} с")

        return str(response.content)

    return StructuredTool.from_function(
        func = describe_picture,
        name = DESCRIBE_PICTURE_TOOL_NAME,
        description = DESCRIBE_PICTURE_DESCRIPTION,
        args_schema = LookAtPictureArguments,
        handle_tool_error = True,
    )


def find_picture(*, project_dir: Path, file_path: str) -> Path:
    """
    Находит картинку проекта по пути от агента. Ошибку для агента поднимает ToolException.

        project_dir: папка проекта.
        file_path: путь от агента, относительно папки проекта.

    Возвращает: Абсолютный путь существующей картинки внутри папки проекта.
    """
    picture_path = (project_dir / file_path).resolve()
    if not picture_path.is_relative_to(project_dir):
        raise ToolException(PICTURE_OUTSIDE_PROJECT_ERROR.format(file_path = file_path))

    if not picture_path.is_file():
        raise ToolException(PICTURE_NOT_FOUND_ERROR.format(file_path = file_path))

    if picture_path.suffix.lower() not in PICTURE_MEDIA_TYPES:
        raise ToolException(NOT_PICTURE_ERROR.format(file_path = file_path, suffixes = ", ".join(PICTURE_MEDIA_TYPES)))

    return picture_path
