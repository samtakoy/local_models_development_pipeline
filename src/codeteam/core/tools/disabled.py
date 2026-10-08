"""Заглушка инструмента: то же имя, описание и аргументы, но любой вызов получает отказ."""

from langchain_core.tools import BaseTool, StructuredTool, ToolException


def build_disabled_tool(*, tool: BaseTool, refusal: str) -> BaseTool:
    """
    Собирает заглушку инструмента: модель видит тот же инструмент, но вызов получает отказ.

        tool: инструмент, который заглушка заменяет.
        refusal: текст отказа для агента.

    Возвращает: Инструмент-заглушку.
    """

    def disabled(**arguments) -> str:
        """
        Отказывает в вызове инструмента.

            arguments: аргументы вызова; не используются.

        Возвращает: Ничего не возвращает: отказ для агента поднимает ToolException.
        """
        raise ToolException(refusal)

    return StructuredTool.from_function(
        func = disabled,
        name = tool.name,
        description = tool.description,
        args_schema = tool.args_schema,
        handle_tool_error = True,
    )
