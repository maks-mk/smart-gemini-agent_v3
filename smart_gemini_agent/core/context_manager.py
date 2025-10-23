"""
Улучшенный менеджер контекста для Smart Gemini Agent
"""

import time
import logging
from typing import Dict, Any, List, Optional, TypedDict
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class ContextType(Enum):
    """Типы контекстной информации"""

    USER_ACTION = "user_action"
    FILE_OPERATION = "file_operation"
    TOOL_USAGE = "tool_usage"
    ERROR_STATE = "error_state"
    SUCCESS_STATE = "success_state"


@dataclass
class ContextEntry:
    """Запись контекста с метаданными"""

    context_type: ContextType
    intent: str
    params: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error_message: Optional[str] = None
    tool_used: Optional[str] = None
    execution_time: float = 0.0
    priority: int = 1  # 1-5, где 5 - наивысший приоритет


class Stats(TypedDict):
    total_entries: int
    success_rate: float
    avg_execution_time: float
    most_used_intents: Dict[str, int]
    error_patterns: Dict[str, int]
    tool_usage_stats: Dict[str, int]


class SmartContextManager:
    """Умный менеджер контекста с приоритизацией и аналитикой"""

    def __init__(self, max_entries: int = 50, debug_mode: bool = False):
        self.max_entries = max_entries
        self.debug_mode = debug_mode

        # Основное хранилище контекста (FIFO с приоритетом)
        self._context_history: deque[ContextEntry] = deque(maxlen=max_entries)

        # Быстрый доступ к последним операциям по типу
        self._last_by_type: Dict[ContextType, ContextEntry] = {}

        # Статистика использования
        self._stats: Stats = {
            "total_entries": 0,
            "success_rate": 0.0,
            "avg_execution_time": 0.0,
            "most_used_intents": {},
            "error_patterns": {},
            "tool_usage_stats": {},
        }

        # Кэш для быстрого поиска похожих операций
        self._similarity_cache: Dict[str, List[ContextEntry]] = {}

        # НОВОЕ: Постоянное хранилище важных данных между запросами
        self._persistent_data: Dict[str, Any] = {
            "user_ids": {},  # имя -> ID пользователя
            "chat_ids": {},  # имя -> ID чата
            "file_paths": {},  # короткое имя -> полный путь
            "last_entities": {},  # последние использованные сущности по типу
            "preferences": {},  # пользовательские предпочтения
        }

    def add_context(
        self,
        context_type: ContextType,
        intent: str,
        params: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
        tool_used: Optional[str] = None,
        execution_time: float = 0.0,
        priority: int = 1,
    ) -> None:
        """Добавление записи в контекст"""

        entry = ContextEntry(
            context_type=context_type,
            intent=intent,
            params=params,
            success=success,
            error_message=error_message,
            tool_used=tool_used,
            execution_time=execution_time,
            priority=priority,
        )

        # Добавляем в основную историю
        self._context_history.append(entry)

        # Обновляем быстрый доступ
        self._last_by_type[context_type] = entry

        # Обновляем статистику
        self._update_stats(entry)

        # Очищаем кэш схожести при добавлении новых данных
        self._similarity_cache.clear()

        if self.debug_mode:
            logger.debug(
                f"Добавлен контекст: {intent} ({context_type.value}), "
                f"успех: {success}, время: {execution_time:.2f}с"
            )

    def get_last_context(
        self, context_type: Optional[ContextType] = None
    ) -> Optional[ContextEntry]:
        """Получение последнего контекста определенного типа или общего"""
        if context_type:
            return self._last_by_type.get(context_type)

        return self._context_history[-1] if self._context_history else None

    def get_similar_operations(
        self, intent: str, params: Dict[str, Any], limit: int = 3
    ) -> List[ContextEntry]:
        """Поиск похожих операций в истории"""
        cache_key = f"{intent}_{hash(str(sorted(params.items())))}"

        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key][:limit]

        similar = []
        target_file = params.get("target")

        for entry in reversed(self._context_history):
            if entry.intent == intent:
                # Точное совпадение намерения
                similarity_score = 3

                # Проверяем схожесть параметров
                if target_file and entry.params.get("target") == target_file:
                    similarity_score += 2  # Тот же файл
                elif target_file and entry.params.get("target"):
                    # Проверяем расширение файла
                    if (
                        target_file.split(".")[-1]
                        == entry.params.get("target", "").split(".")[-1]
                    ):
                        similarity_score += 1

                # Учитываем успешность операции
                if entry.success:
                    similarity_score += 1

                similar.append((similarity_score, entry))

        # Сортируем по релевантности
        similar.sort(key=lambda x: x[0], reverse=True)
        result = [entry for _, entry in similar[:limit]]

        self._similarity_cache[cache_key] = result
        return result

    def get_context_suggestions(
        self, current_intent: str, current_params: Dict[str, Any]
    ) -> List[str]:
        """Получение предложений на основе контекста"""
        suggestions = []

        # Анализируем последние неудачные операции
        recent_errors = [
            entry
            for entry in list(self._context_history)[-10:]
            if not entry.success and entry.intent == current_intent
        ]

        if recent_errors:
            suggestions.append("⚠️ Обнаружены недавние ошибки с этой операцией")

            # Группируем ошибки по типам
            error_types: Dict[str, int] = {}
            for error in recent_errors:
                error_msg = error.error_message or "Неизвестная ошибка"
                error_types[error_msg] = error_types.get(error_msg, 0) + 1

            most_common_error = max(error_types.items(), key=lambda x: x[1])
            suggestions.append(f"Частая ошибка: {most_common_error[0]}")

        # Предлагаем альтернативные инструменты
        similar_ops = self.get_similar_operations(current_intent, current_params)
        successful_tools = [
            op.tool_used for op in similar_ops if op.success and op.tool_used
        ]

        if successful_tools:
            most_successful_tool = max(
                set(successful_tools), key=successful_tools.count
            )
            suggestions.append(f"💡 Рекомендуемый инструмент: {most_successful_tool}")

        return suggestions

    def get_performance_insights(self) -> Dict[str, Any]:
        """Получение аналитики производительности"""
        if not self._context_history:
            return {"message": "Недостаточно данных для анализа"}

        # Анализ по намерениям
        intent_stats: Dict[str, Dict[str, Any]] = {}
        for entry in self._context_history:
            intent = entry.intent
            if intent not in intent_stats:
                intent_stats[intent] = {
                    "total": 0,
                    "successful": 0,
                    "avg_time": 0.0,
                    "times": [],
                }

            intent_stats[intent]["total"] += 1
            if entry.success:
                intent_stats[intent]["successful"] += 1
            intent_stats[intent]["times"].append(entry.execution_time)

        # Вычисляем средние времена и успешность
        for intent, stats in intent_stats.items():
            stats["success_rate"] = (stats["successful"] / stats["total"]) * 100
            stats["avg_time"] = sum(stats["times"]) / len(stats["times"])
            del stats["times"]  # Удаляем сырые данные

        # Находим проблемные области
        problematic_intents = [
            intent
            for intent, stats in intent_stats.items()
            if stats["success_rate"] < 80 and stats["total"] >= 3
        ]

        return {
            "total_operations": len(self._context_history),
            "overall_success_rate": self._stats["success_rate"],
            "avg_execution_time": self._stats["avg_execution_time"],
            "intent_statistics": intent_stats,
            "problematic_intents": problematic_intents,
            "most_used_tools": self._stats["tool_usage_stats"],
        }

    def clear_context(self, keep_stats: bool = True) -> None:
        """Очистка контекста с возможностью сохранения статистики"""
        self._context_history.clear()
        self._last_by_type.clear()
        self._similarity_cache.clear()

        if not keep_stats:
            self._stats = {
                "total_entries": 0,
                "success_rate": 0.0,
                "avg_execution_time": 0.0,
                "most_used_intents": {},
                "error_patterns": {},
                "tool_usage_stats": {},
            }

        logger.info(
            "Контекст очищен" + (" (статистика сохранена)" if keep_stats else "")
        )

    def export_context(self, format_type: str = "json") -> str:
        """Экспорт контекста в различных форматах"""
        if format_type == "json":
            import json

            data = {
                "context_history": [
                    {
                        "type": entry.context_type.value,
                        "intent": entry.intent,
                        "params": entry.params,
                        "timestamp": entry.timestamp,
                        "success": entry.success,
                        "error_message": entry.error_message,
                        "tool_used": entry.tool_used,
                        "execution_time": entry.execution_time,
                    }
                    for entry in self._context_history
                ],
                "statistics": self._stats,
            }
            return json.dumps(data, indent=2, ensure_ascii=False)

        elif format_type == "markdown":
            lines = ["# Контекст агента\n"]
            lines.append(f"Всего операций: {len(self._context_history)}\n")
            lines.append(f"Общий процент успеха: {self._stats['success_rate']:.1f}%\n")

            for entry in self._context_history:
                status = "✅" if entry.success else "❌"
                lines.append(
                    f"- {status} **{entry.intent}** ({entry.context_type.value})"
                )
                if entry.params.get("target"):
                    lines.append(f"  - Цель: `{entry.params['target']}`")
                if entry.tool_used:
                    lines.append(f"  - Инструмент: {entry.tool_used}")
                if not entry.success and entry.error_message:
                    lines.append(f"  - Ошибка: {entry.error_message}")
                lines.append("")

            return "\n".join(lines)

        else:
            raise ValueError(f"Неподдерживаемый формат: {format_type}")

    def _update_stats(self, entry: ContextEntry) -> None:
        """Обновление статистики"""
        self._stats["total_entries"] += 1

        # Обновляем процент успеха
        total = self._stats["total_entries"]
        current_successes = sum(1 for e in self._context_history if e.success)
        self._stats["success_rate"] = (current_successes / total) * 100

        # Обновляем среднее время выполнения
        total_time = sum(e.execution_time for e in self._context_history)
        self._stats["avg_execution_time"] = total_time / total

        # Обновляем статистику намерений
        intent = entry.intent
        self._stats["most_used_intents"][intent] = (
            self._stats["most_used_intents"].get(intent, 0) + 1
        )

        # Обновляем статистику инструментов
        if entry.tool_used:
            tool = entry.tool_used
            self._stats["tool_usage_stats"][tool] = (
                self._stats["tool_usage_stats"].get(tool, 0) + 1
            )

        # Обновляем паттерны ошибок
        if not entry.success and entry.error_message:
            error = entry.error_message
            self._stats["error_patterns"][error] = (
                self._stats["error_patterns"].get(error, 0) + 1
            )

    # НОВЫЕ МЕТОДЫ для работы с постоянными данными

    def store_user_id(self, name: str, user_id: str) -> None:
        """Сохранение ID пользователя для будущего использования"""
        self._persistent_data["user_ids"][name.lower()] = user_id
        if self.debug_mode:
            logger.debug(f"Сохранен ID пользователя: {name} -> {user_id}")

    def get_user_id(self, name: str) -> Optional[str]:
        """Получение сохраненного ID пользователя"""
        return self._persistent_data["user_ids"].get(name.lower())

    def store_chat_id(self, name: str, chat_id: str) -> None:
        """Сохранение ID чата для будущего использования"""
        self._persistent_data["chat_ids"][name.lower()] = chat_id
        self._persistent_data["last_entities"]["chat"] = chat_id
        if self.debug_mode:
            logger.debug(f"Сохранен ID чата: {name} -> {chat_id}")

    def get_chat_id(self, name: str) -> Optional[str]:
        """Получение сохраненного ID чата"""
        return self._persistent_data["chat_ids"].get(name.lower())

    def get_last_chat(self) -> Optional[str]:
        """Получение последнего использованного чата"""
        return self._persistent_data["last_entities"].get("chat")

    def store_file_path(self, short_name: str, full_path: str) -> None:
        """Сохранение полного пути к файлу"""
        self._persistent_data["file_paths"][short_name.lower()] = full_path
        if self.debug_mode:
            logger.debug(f"Сохранен путь к файлу: {short_name} -> {full_path}")

    def get_file_path(self, short_name: str) -> Optional[str]:
        """Получение полного пути к файлу"""
        return self._persistent_data["file_paths"].get(short_name.lower())

    def extract_and_store_entities(self, tool_result: Any, tool_name: str) -> None:
        """Автоматическое извлечение и сохранение сущностей из результатов инструментов"""
        if not tool_result:
            return

        try:
            # Обработка результатов поиска диалогов
            if tool_name == "search_dialogs" and hasattr(tool_result, "dialogs"):
                for dialog in tool_result.dialogs:
                    if hasattr(dialog, "name") and hasattr(dialog, "id"):
                        self.store_user_id(dialog.name, str(dialog.id))
                    if hasattr(dialog, "username") and hasattr(dialog, "id"):
                        self.store_user_id(
                            dialog.username.replace("@", ""), str(dialog.id)
                        )

            # Обработка результатов отправки сообщений
            elif tool_name == "send_message":
                # Сохраняем последний использованный чат
                if hasattr(tool_result, "chat_id"):
                    self._persistent_data["last_entities"]["chat"] = str(
                        tool_result.chat_id
                    )

            # Обработка файловых операций
            elif "file" in tool_name.lower():
                if hasattr(tool_result, "path"):
                    import os

                    filename = os.path.basename(tool_result.path)
                    self.store_file_path(filename, tool_result.path)

        except Exception as e:
            if self.debug_mode:
                logger.debug(f"Ошибка извлечения сущностей из {tool_name}: {e}")

    def get_context_for_intent(
        self, intent: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Получение релевантного контекста для намерения"""
        context = {}

        # Для Telegram операций
        if "message" in intent or "telegram" in intent:
            # Добавляем известные ID пользователей
            if self._persistent_data["user_ids"]:
                context["known_users"] = self._persistent_data["user_ids"]

            # Добавляем последний чат
            last_chat = self.get_last_chat()
            if last_chat:
                context["last_chat"] = last_chat

        # Для файловых операций
        elif "file" in intent:
            if self._persistent_data["file_paths"]:
                context["known_files"] = self._persistent_data["file_paths"]

        # Добавляем похожие успешные операции
        similar_ops = self.get_similar_operations(intent, params, limit=2)
        if similar_ops:
            context["similar_successful_operations"] = [
                {
                    "params": op.params,
                    "tool_used": op.tool_used,
                    "execution_time": op.execution_time,
                }
                for op in similar_ops
                if op.success
            ]

        return context

    def get_persistent_data_summary(self) -> Dict[str, Any]:
        """Получение сводки постоянных данных"""
        return {
            "stored_users": len(self._persistent_data["user_ids"]),
            "stored_chats": len(self._persistent_data["chat_ids"]),
            "stored_files": len(self._persistent_data["file_paths"]),
            "last_entities": self._persistent_data["last_entities"].copy(),
            "user_list": list(self._persistent_data["user_ids"].keys()),
            "chat_list": list(self._persistent_data["chat_ids"].keys()),
        }
