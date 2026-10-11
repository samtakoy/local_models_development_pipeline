"""Статистика запуска агента: шаги, запросы к модели, инструменты по фазам, фаза черновика.

Получает те же события графа, что и журнал: {имя узла: {"messages": [...]}}. События, которых в потоке
нет (повторы запросов, срабатывания хуков), прибавляются явными счётчиками. В конце работы агента
пишется файлом JSON рядом с журналом.
"""

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from codeteam.core.agent.journal import NANOSECONDS_PER_SECOND
from codeteam.core.agent.node_ids import AGENT_NODE_ID, ANSWER_NOTICE_NODE_ID, DRAFT_AGENT_NODE_ID, \
    DRAFT_TOOL_NODE_ID, INIT_NODE_ID, LIMIT_NOTICE_NODE_ID, REINIT_NODE_ID, TOOL_NODE_ID

# Окончание имени файла статистики: <журнал агента>.stats.json рядом с журналом.
STATISTICS_FILE_SUFFIX = ".stats.json"

# Фазы работы агента: разогрев (вызовы инструментов после init и reinit), работа, черновик.
WARMUP_PHASE = "warmup"
WORK_PHASE = "work"
DRAFT_PHASE = "draft"

# Фаза по узлу графа.
NODE_PHASES = {
    INIT_NODE_ID: WARMUP_PHASE,
    REINIT_NODE_ID: WARMUP_PHASE,
    AGENT_NODE_ID: WORK_PHASE,
    TOOL_NODE_ID: WORK_PHASE,
    ANSWER_NOTICE_NODE_ID: WORK_PHASE,
    LIMIT_NOTICE_NODE_ID: DRAFT_PHASE,
    DRAFT_AGENT_NODE_ID: DRAFT_PHASE,
    DRAFT_TOOL_NODE_ID: DRAFT_PHASE,
}

# Узлы ответа модели и узлы инструментов.
AGENT_NODE_IDS = (AGENT_NODE_ID, DRAFT_AGENT_NODE_ID)
TOOL_NODE_IDS = (TOOL_NODE_ID, DRAFT_TOOL_NODE_ID)

# События, которые статистика выводит из потока: замечание о лимите, сброс истории,
# подсказка после ответа без инструмента и без DONE.
LIMIT_NOTICE_EVENT = "limit_notices"
RESET_EVENT = "resets"
UNFINISHED_ANSWER_HINT_EVENT = "unfinished_answer_hints"

# Явные счётчики событий, которых нет в потоке: повтор запроса после ошибки сервера ollama, тихий повтор
# запроса после ответа без инструмента и без DONE, замечания хуков к файлам своих папок, замечания проверок
# после шага (например, откат правок проекта), замечание на попытку сдать работу командой.
SERVER_ERROR_RETRY_COUNTER = "server_error_retries"
UNFINISHED_ANSWER_RETRY_COUNTER = "unfinished_answer_retries"
STEP_HOOK_REMARK_COUNTER = "step_hook_remarks"
STEP_CHECK_REMARK_COUNTER = "step_check_remarks"
ANSWER_COMMAND_REMARK_COUNTER = "answer_command_remarks"

# Явные счётчики петель по фазам: замечания на одинаковый результат инструментов подряд и остановки петли
# после последнего замечания: в фазе работы — переход в фазу черновика, в фазе черновика — пересборка истории.
REPEATED_RESULT_REMARK_COUNTER = "repeated_result_remarks"
REPEATED_RESULT_STOP_COUNTER = "repeated_result_stops"

# Явные счётчики опасных переходов: переход в фазу черновика по жёсткому лимиту истории, сброс истории,
# когда история дошла до края окна модели в фазе черновика, сброс после того, как кончились попытки сдать работу.
HARD_LIMIT_COUNTER = "hard_limit_notices"
WINDOW_FULL_RESET_COUNTER = "window_full_resets"
ANSWER_NOTICE_RESET_COUNTER = "answer_notice_resets"

# Знаков после запятой у секунд и скоростей в файле.
ROUND_DIGITS = 3


class AgentStatistics:
    """
    Статистика одного запуска агента.
    """

    def __init__(
        self,
        *,
        role_name: str,
        journal_name: str,
        model_name: str,
        reasoning_level: str,
        context_window: int,
    ) -> None:
        """
        Начинает статистику запуска.

            role_name: имя роли агента.
            journal_name: имя журнала агента без расширения.
            model_name: имя модели агента.
            reasoning_level: уровень размышления модели агента.
            context_window: окно модели, токены: вход и выход запроса вместе.
        """
        self._role_name = role_name
        self._journal_name = journal_name
        self._model_name = model_name
        self._reasoning_level = reasoning_level
        self._context_window = context_window
        self._started_at = datetime.now()
        self._started_monotonic = time.monotonic()
        self._step_counts: Counter[str] = Counter()
        self._requests: list[dict[str, Any]] = []
        # инструмент -> фаза -> вызовы и ошибки
        self._tool_counts: dict[str, dict[str, Counter[str]]] = {}
        self._events: Counter[str] = Counter()
        self._counters: Counter[str] = Counter()
        # счётчик -> фаза -> число
        self._phase_counters: dict[str, Counter[str]] = {}
        self._previous_node: str | None = None
        self._draft_started: float | None = None
        self._draft_seconds = 0.0
        self._awaits_first_draft_response = False
        self._first_draft_response_seconds: list[float] = []
        self._draft_error_streak = 0
        self._draft_error_streak_max = 0
        self._error: str | None = None

    def record(self, *, event: dict[str, Any]) -> None:
        """
        Учитывает шаг графа.

            event: событие графа в режиме updates.
        """
        for node_name, update in event.items():
            messages = update.get("messages", []) if isinstance(update, dict) else []
            self._step_counts[node_name] += 1
            if node_name == LIMIT_NOTICE_NODE_ID:
                self._start_draft()
            elif node_name == REINIT_NODE_ID:
                self._events[RESET_EVENT] += 1
                self._stop_draft()

            phase = self._phase(node_name = node_name)
            for message in messages:
                if isinstance(message, AIMessage) and message.usage_metadata:
                    self._record_request(node_name = node_name, message = message)
                elif isinstance(message, HumanMessage) and node_name in AGENT_NODE_IDS:
                    # узел ответа добавляет сообщение человека только как подсказку после ответа без инструмента
                    self._events[UNFINISHED_ANSWER_HINT_EVENT] += 1
                elif isinstance(message, ToolMessage) and node_name in TOOL_NODE_IDS:
                    self._record_tool_result(phase = phase, message = message)

            self._previous_node = node_name

    def count(self, *, name: str) -> None:
        """
        Прибавляет событие, которого нет в потоке событий графа.

            name: имя события.
        """
        self._counters[name] += 1

    def count_in_phase(self, *, name: str, phase: str) -> None:
        """
        Прибавляет событие фазы, которого нет в потоке событий графа.

            name: имя события.
            phase: фаза работы агента.
        """
        self._phase_counters.setdefault(name, Counter())[phase] += 1

    def fail(self, *, error: Exception) -> None:
        """
        Запоминает ошибку, прервавшую запуск.

            error: исключение.
        """
        self._error = f"{type(error).__name__}: {error}"

    def write(self, *, path: Path) -> None:
        """
        Пишет статистику файлом JSON.

            path: файл статистики.
        """
        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii = False, indent = 2), encoding = "utf-8")

    def to_dict(self) -> dict[str, Any]:
        """
        Собирает статистику словарём.

        Возвращает: Роль, журнал, модель, уровень размышления, окно модели, время, шаги по узлам, запросы к модели
            и их сумму, инструменты по фазам, события, явные счётчики, явные счётчики по фазам, фазу черновика
            и ошибку запуска.
        """
        now = time.monotonic()
        draft_seconds = self._draft_seconds
        if self._draft_started is not None:
            draft_seconds += now - self._draft_started

        return {
            # роль агента: по ней отчёт собирает средние роли
            "role": self._role_name,
            # имя журнала: экземпляр агента _rN
            "journal": self._journal_name,
            # модель агента
            "model_name": self._model_name,
            # уровень размышления модели
            "reasoning_level": self._reasoning_level,
            # окно модели, токены: по нему отчёт находит переполнение
            "context_window": self._context_window,
            # время старта агента
            "started_at": self._started_at.isoformat(timespec = "seconds"),
            # время работы агента вместе с его помощниками, секунды
            "elapsed_seconds": round(now - self._started_monotonic, ROUND_DIGITS),
            # ошибка, прервавшая агента; None — агент закончил работу сам
            "error": self._error,
            # шаги по узлам графа: сколько раз отработал каждый узел
            "steps": dict(self._step_counts),
            # запросы к модели: число, токены вход и выход, время ответов
            "model_requests": {
                "count": len(self._requests),
                "input_tokens": sum(request["input_tokens"] for request in self._requests),
                "output_tokens": sum(request["output_tokens"] for request in self._requests),
                "seconds": round(sum(request["seconds"] for request in self._requests), ROUND_DIGITS),
            },
            # каждый запрос к модели по порядку: для скорости по размеру контекста и наибольшего контекста
            "requests": self._requests,
            # инструменты: вызовы и ошибки по фазам — разогрев, работа, черновик
            "tools": {
                tool_name: {phase: dict(counts) for phase, counts in phases.items()}
                for tool_name, phases in self._tool_counts.items()
            },
            # события из потока графа: переходы по лимиту, сбросы истории, подсказки после ответа без инструмента
            "events": dict(self._events),
            # явные счётчики: повторы запроса к ollama, тихие повторы, хуки, проверки, опасные переходы
            "counters": dict(self._counters),
            # явные счётчики по фазам: замечания и остановки петель
            "phase_counters": {name: dict(phases) for name, phases in self._phase_counters.items()},
            # фаза черновика: время, время первого ответа после лимита, самая длинная серия ошибок подряд
            "draft": {
                "seconds": round(draft_seconds, ROUND_DIGITS),
                "first_response_seconds": self._first_draft_response_seconds,
                "error_streak_max": self._draft_error_streak_max,
            },
        }

    def _phase(self, *, node_name: str) -> str:
        """
        Определяет фазу шага: инструменты сразу после init и reinit — разогрев.

            node_name: имя узла графа.

        Возвращает: Фазу шага.
        """
        if node_name == TOOL_NODE_ID and self._previous_node in (INIT_NODE_ID, REINIT_NODE_ID):
            return WARMUP_PHASE

        return NODE_PHASES.get(node_name, WORK_PHASE)

    def _start_draft(self) -> None:
        """
        Отмечает начало фазы черновика: замечание о лимите.
        """
        self._events[LIMIT_NOTICE_EVENT] += 1
        self._awaits_first_draft_response = True
        if self._draft_started is None:
            self._draft_started = time.monotonic()

    def _stop_draft(self) -> None:
        """
        Отмечает конец фазы черновика: сброс истории.
        """
        if self._draft_started is not None:
            self._draft_seconds += time.monotonic() - self._draft_started
            self._draft_started = None

    def _record_request(self, *, node_name: str, message: AIMessage) -> None:
        """
        Учитывает запрос к модели: токены, время ответа, скорость вывода.

            node_name: узел ответа модели.
            message: ответ модели с usage_metadata.
        """
        metadata = message.response_metadata
        seconds = metadata.get("total_duration", 0) / NANOSECONDS_PER_SECOND
        eval_seconds = metadata.get("eval_duration", 0) / NANOSECONDS_PER_SECOND
        output_tokens = message.usage_metadata["output_tokens"]
        self._requests.append({
            # узел ответа: работа или черновик
            "node": node_name,
            # вся история на входе запроса, токены
            "input_tokens": message.usage_metadata["input_tokens"],
            # ответ модели, токены
            "output_tokens": output_tokens,
            # время ответа целиком, секунды
            "seconds": round(seconds, ROUND_DIGITS),
            # скорость генерации ответа; None — ollama не дала время генерации
            "tokens_per_second": round(output_tokens / eval_seconds, ROUND_DIGITS) if eval_seconds else None,
            # инструменты, которые вызвал ответ
            "tool_calls": [call["name"] for call in message.tool_calls],
        })
        if node_name == DRAFT_AGENT_NODE_ID and self._awaits_first_draft_response:
            self._first_draft_response_seconds.append(round(seconds, ROUND_DIGITS))
            self._awaits_first_draft_response = False

    def _record_tool_result(self, *, phase: str, message: ToolMessage) -> None:
        """
        Учитывает результат вызова инструмента и серию ошибок подряд в фазе черновика.

            phase: фаза шага.
            message: результат инструмента.
        """
        is_error = message.status == "error"
        counts = self._tool_counts.setdefault(str(message.name), {}).setdefault(phase, Counter())
        counts["calls"] += 1
        if is_error:
            counts["errors"] += 1

        if phase != DRAFT_PHASE:
            return

        self._draft_error_streak = self._draft_error_streak + 1 if is_error else 0
        self._draft_error_streak_max = max(self._draft_error_streak_max, self._draft_error_streak)
