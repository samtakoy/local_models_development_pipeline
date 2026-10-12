"""Проверка повторов шага инструментов: по результатам (те же вызовы с тем же результатом) и по вызовам (те же
вызовы с любым результатом). Замечания агенту и остановка петли."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from codeteam.core.agent.prompts import REPEATED_CALL_REMARKS, REPEATED_CALL_STOP_REMARK, REPEATED_RESULT_REMARKS, \
    REPEATED_RESULT_STOP_REMARK
from codeteam.core.agent.statistics import REPEATED_CALL_REMARK_COUNTER, REPEATED_CALL_STOP_COUNTER, \
    REPEATED_RESULT_REMARK_COUNTER, REPEATED_RESULT_STOP_COUNTER, AgentStatistics

# Сколько прошлых шагов инструментов помнит проверка повторов: повтор — тот же шаг среди них, так ловится и петля
# из нескольких чередующихся вызовов.
REPEAT_WINDOW = 2 # 5


@dataclass(frozen = True)
class RepeatCheck:
    """
    Проверка повторов шага подряд: сколько повторов без замечаний, замечания и остановка.

        silent_repeats: сколько повторов подряд проходят без замечаний.
        remarks: замечания на следующие повторы подряд, по одному на повтор.
        stop_remark: замечание на повтор, который останавливает петлю.
        remark_counter: имя счётчика статистики замечаний.
        stop_counter: имя счётчика статистики остановок.
    """

    silent_repeats: int
    remarks: tuple[str, ...]
    stop_remark: str
    remark_counter: str
    stop_counter: str

    @property
    def limit(self) -> int:
        """
        Число повторов подряд, на котором петля останавливается.
        """
        return self.silent_repeats + len(self.remarks) + 1


# Повторы по результатам: замечания с первого повтора.
RESULT_REPEAT_CHECK = RepeatCheck(
    silent_repeats = 0,
    remarks = REPEATED_RESULT_REMARKS,
    stop_remark = REPEATED_RESULT_STOP_REMARK,
    remark_counter = REPEATED_RESULT_REMARK_COUNTER,
    stop_counter = REPEATED_RESULT_STOP_COUNTER,
)

# Повторы по вызовам: первые повторы без замечаний, остановка позже, чем по результатам.
CALL_REPEAT_CHECK = RepeatCheck(
    silent_repeats = 4,
    remarks = REPEATED_CALL_REMARKS,
    stop_remark = REPEATED_CALL_STOP_REMARK,
    remark_counter = REPEATED_CALL_REMARK_COUNTER,
    stop_counter = REPEATED_CALL_STOP_COUNTER,
)


@dataclass(frozen = True)
class RepeatState:
    """
    Состояние проверки повторов по результатам, которое нельзя восстановить по истории: в истории к результатам
    дописаны замечания.

        repeated_results: сколько шагов подряд повторили результат одного из REPEAT_WINDOW прошлых шагов.
        recent_result_keys: ключи результатов последних REPEAT_WINDOW шагов.
    """

    repeated_results: int
    recent_result_keys: tuple[str, ...]


# Состояние проверки повторов на старте и после перехода к новой фазе.
INITIAL_REPEAT_STATE = RepeatState(repeated_results = 0, recent_result_keys = ())


@dataclass(frozen = True)
class RepeatStep:
    """
    Итог проверки повторов шага инструментов.

        repeats: состояние проверки повторов после шага.
        remark: замечание агенту или None.
    """

    repeats: RepeatState
    remark: str | None


def check_repeats(
    *,
    repeats: RepeatState,
    messages: Sequence[BaseMessage],
    tool_messages: Sequence[BaseMessage],
    statistics: AgentStatistics,
    phase: str,
) -> RepeatStep:
    """
    Проверяет шаг инструментов на повтор и выбирает одно замечание: остановка петли, затем замечание по
    результатам, затем по вызовам. Считает замечание в статистике фазы.

        repeats: состояние проверки повторов до шага.
        messages: история агента; последнее сообщение — ответ модели с вызовами шага.
        tool_messages: сообщения шага узла инструментов, до замечаний.
        statistics: статистика агента.
        phase: фаза работы агента.

    Возвращает: Состояние проверки повторов после шага и замечание.
    """
    result_key = _step_result_key(response = messages[-1], tool_messages = tool_messages)
    repeated_results = repeats.repeated_results + 1 if result_key in repeats.recent_result_keys else 0
    counts = (
        (RESULT_REPEAT_CHECK, repeated_results),
        (CALL_REPEAT_CHECK, count_repeated_calls(messages = messages)),
    )

    return RepeatStep(
        repeats = RepeatState(
            repeated_results = repeated_results,
            recent_result_keys = (*repeats.recent_result_keys, result_key)[-REPEAT_WINDOW:],
        ),
        remark = _repeat_remark(counts = counts, statistics = statistics, phase = phase),
    )


def is_looped(*, repeats: RepeatState, messages: Sequence[BaseMessage]) -> bool:
    """
    Проверяет, что одна из проверок повторов дошла до остановки.

        repeats: состояние проверки повторов.
        messages: история агента.

    Возвращает: True, если повторов по результатам или по вызовам подряд не меньше предела проверки.
    """
    return (
        repeats.repeated_results >= RESULT_REPEAT_CHECK.limit
        or count_repeated_calls(messages = messages) >= CALL_REPEAT_CHECK.limit
    )


def count_repeated_calls(*, messages: Sequence[BaseMessage]) -> int:
    """
    Считает по истории, сколько последних ответов модели подряд повторили вызовы предыдущего ответа с вызовами.

        messages: история агента.

    Возвращает: Число повторов подряд; 0, если последний ответ с вызовами не повтор.
    """
    calls = [
        _calls(response = message)
        for message in messages
        if isinstance(message, AIMessage) and message.tool_calls
    ]

    return _count_last_call_repeats(items = calls)


def _count_last_call_repeats(*, items: list) -> int:
    """
    Считает, сколько элементов подряд перед последним равны последнему.

        items: элементы по порядку.

    Возвращает: Число равных последнему подряд; 0 для пустого списка.
    """
    same_count = 0
    for item in reversed(items[:-1]):
        if item != items[-1]:
            break
        same_count += 1

    return same_count


def _repeat_remark(
    *,
    counts: tuple[tuple[RepeatCheck, int], ...],
    statistics: AgentStatistics,
    phase: str,
) -> str | None:
    """
    Выбирает одно замечание на повтор и считает его в статистике фазы.

        counts: проверки по порядку важности и число повторов подряд по каждой.
        statistics: статистика агента.
        phase: фаза работы агента.

    Возвращает: Замечание об остановке первой проверки, дошедшей до предела; иначе замечание первой проверки,
        у которой повторов больше, чем без замечаний; иначе None.
    """
    for check, count in counts:
        if count >= check.limit:
            statistics.count_in_phase(name = check.stop_counter, phase = phase)
            return check.stop_remark

    for check, count in counts:
        if count > check.silent_repeats:
            statistics.count_in_phase(name = check.remark_counter, phase = phase)
            return check.remarks[count - check.silent_repeats - 1]

    return None


def _calls(*, response: AIMessage) -> list[tuple[str, dict]]:
    """
    Собирает вызовы ответа модели для сравнения с другими ответами.

        response: ответ модели с вызовами инструментов.

    Возвращает: Имя и аргументы каждого вызова.
    """
    return [(call["name"], call["args"]) for call in response.tool_calls]


def _step_result_key(*, response: BaseMessage, tool_messages: Sequence[BaseMessage]) -> str:
    """
    Собирает шаг инструментов в строку для сравнения с прошлыми шагами: вызовы и их результаты.

        response: ответ модели с вызовами инструментов.
        tool_messages: сообщения шага узла инструментов, до замечаний.

    Возвращает: Имя, аргументы и текст результата каждого вызова строкой JSON.
    """
    arguments = {call["id"]: call["args"] for call in getattr(response, "tool_calls", [])}
    steps = [
        [str(message.name), arguments.get(message.tool_call_id), message.text]
        for message in tool_messages
        if isinstance(message, ToolMessage)
    ]

    return json.dumps(steps, ensure_ascii = False, sort_keys = True)
