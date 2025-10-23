"""
Система восстановления после ошибок и интеллектуальной обработки сбоев
с оптимизированной производительностью
"""

import logging
import re
from typing import Dict, List, Any, Tuple, Optional, TypedDict, Pattern
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Предкомпилированные регулярные выражения для производительности
_TIME_PATTERN = re.compile(r"(\d+)\s*(second|sec|секунд)", re.IGNORECASE)
_RETRY_DELAY_PATTERN = re.compile(r"retry_delay\s*{\s*seconds:\s*(\d+)")
_FILE_PATH_PATTERN = re.compile(r"['\"]([^'\"]+)['\"]")


class ErrorType(Enum):
    """Типы ошибок для классификации"""

    TOOL_ERROR = "tool_error"
    VALIDATION_ERROR = "validation_error"
    PERMISSION_ERROR = "permission_error"
    NOT_FOUND_ERROR = "not_found_error"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    SYNTAX_ERROR = "syntax_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorPattern:
    """Паттерн ошибки для распознавания"""

    pattern: str
    error_type: ErrorType
    recovery_strategy: str
    confidence: float = 1.0


@dataclass
class RecoveryAction:
    """Действие для восстановления после ошибки"""

    action_type: str
    description: str
    parameters: Dict[str, Any]
    priority: int = 1


class ErrorStats(TypedDict):
    total_errors: int
    recovered_errors: int
    error_types: Dict[str, int]
    recovery_success_rate: float


class ErrorRecoverySystem:
    """Система интеллектуального восстановления после ошибок"""

    def __init__(self, context_manager=None, debug_mode: bool = False):
        self.context_manager = context_manager
        self.debug_mode = debug_mode

        # Паттерны для распознавания ошибок
        self.error_patterns = self._initialize_error_patterns()
        
        # Предкомпилированные паттерны для производительности
        self._compiled_error_patterns: List[Tuple[Pattern, ErrorType, float]] = []
        self._compile_error_patterns()

        # Статистика ошибок
        self.error_stats: ErrorStats = {
            "total_errors": 0,
            "recovered_errors": 0,
            "error_types": {},
            "recovery_success_rate": 0.0,
        }

        # Кэш стратегий восстановления
        self.recovery_cache: Dict[str, List[RecoveryAction]] = {}

    def _compile_error_patterns(self) -> None:
        """Предкомпиляция регулярных выражений для error паттернов"""
        self._compiled_error_patterns = [
            (re.compile(ep.pattern, re.IGNORECASE), ep.error_type, ep.confidence)
            for ep in self.error_patterns
        ]
        logger.debug(f"Скомпилировано {len(self._compiled_error_patterns)} паттернов ошибок")

    def _initialize_error_patterns(self) -> List[ErrorPattern]:
        """Инициализация паттернов ошибок"""
        return [
            # Ошибки файловой системы
            ErrorPattern(
                pattern=r"(file not found|no such file|файл не найден)",
                error_type=ErrorType.NOT_FOUND_ERROR,
                recovery_strategy="suggest_alternatives",
                confidence=0.9,
            ),
            ErrorPattern(
                pattern=r"(permission denied|access denied|доступ запрещен)",
                error_type=ErrorType.PERMISSION_ERROR,
                recovery_strategy="suggest_safe_alternative",
                confidence=0.95,
            ),
            ErrorPattern(
                pattern=r"(invalid path|недопустимый путь|illegal characters)",
                error_type=ErrorType.VALIDATION_ERROR,
                recovery_strategy="fix_path_format",
                confidence=0.9,
            ),
            # Сетевые ошибки
            ErrorPattern(
                pattern=r"(connection error|network error|timeout|сетевая ошибка)",
                error_type=ErrorType.NETWORK_ERROR,
                recovery_strategy="retry_with_backoff",
                confidence=0.8,
            ),
            ErrorPattern(
                pattern=r"(rate limit|too many requests|превышен лимит)",
                error_type=ErrorType.RATE_LIMIT_ERROR,
                recovery_strategy="wait_and_retry",
                confidence=0.95,
            ),
            # Ошибки инструментов
            ErrorPattern(
                pattern=r"(tool error|command failed|инструмент недоступен)",
                error_type=ErrorType.TOOL_ERROR,
                recovery_strategy="try_alternative_tool",
                confidence=0.85,
            ),
            ErrorPattern(
                pattern=r"(syntax error|invalid syntax|синтаксическая ошибка)",
                error_type=ErrorType.SYNTAX_ERROR,
                recovery_strategy="fix_syntax",
                confidence=0.9,
            ),
        ]

    def analyze_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> Tuple[ErrorType, List[RecoveryAction]]:
        """
        Анализ ошибки и генерация стратегий восстановления

        Args:
            error_message: Сообщение об ошибке
            context: Контекст выполнения (намерение, параметры и т.д.)

        Returns:
            Tuple[тип_ошибки, список_действий_восстановления]
        """
        self.error_stats["total_errors"] += 1

        # Классифицируем ошибку
        error_type = self._classify_error(error_message)

        # Обновляем статистику
        self.error_stats["error_types"][error_type.value] = (
            self.error_stats["error_types"].get(error_type.value, 0) + 1
        )

        # Генерируем стратегии восстановления
        recovery_actions = self._generate_recovery_actions(
            error_type, error_message, context
        )

        if self.debug_mode:
            logger.info(
                f"🔍 Анализ ошибки: тип={error_type.value}, "
                f"стратегий восстановления={len(recovery_actions)}"
            )

        return error_type, recovery_actions

    def _classify_error(self, error_message: str) -> ErrorType:
        """Классификация ошибки по паттернам (оптимизированная версия)"""
        error_lower = error_message.lower()

        best_error_type = ErrorType.UNKNOWN_ERROR
        best_confidence = 0.0

        for compiled_pattern, error_type, confidence in self._compiled_error_patterns:
            if compiled_pattern.search(error_lower):
                if confidence > best_confidence:
                    best_error_type = error_type
                    best_confidence = confidence

        return best_error_type

    def _generate_recovery_actions(
        self, error_type: ErrorType, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Генерация действий для восстановления"""

        # Проверяем кэш
        cache_key = f"{error_type.value}_{hash(error_message)}"
        if cache_key in self.recovery_cache:
            return self.recovery_cache[cache_key]

        actions = []

        if error_type == ErrorType.NOT_FOUND_ERROR:
            actions.extend(self._handle_not_found_error(error_message, context))

        elif error_type == ErrorType.PERMISSION_ERROR:
            actions.extend(self._handle_permission_error(error_message, context))

        elif error_type == ErrorType.VALIDATION_ERROR:
            actions.extend(self._handle_validation_error(error_message, context))

        elif error_type == ErrorType.NETWORK_ERROR:
            actions.extend(self._handle_network_error(error_message, context))

        elif error_type == ErrorType.RATE_LIMIT_ERROR:
            actions.extend(self._handle_rate_limit_error(error_message, context))

        elif error_type == ErrorType.TOOL_ERROR:
            actions.extend(self._handle_tool_error(error_message, context))

        elif error_type == ErrorType.SYNTAX_ERROR:
            actions.extend(self._handle_syntax_error(error_message, context))

        else:
            actions.extend(self._handle_unknown_error(error_message, context))

        # Кэшируем результат
        self.recovery_cache[cache_key] = actions

        return actions

    def _handle_not_found_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка ошибок 'файл не найден'"""
        actions = []

        # Извлекаем имя файла из ошибки (используем предкомпилированный паттерн)
        file_match = _FILE_PATH_PATTERN.search(error_message)
        if file_match:
            missing_file = file_match.group(1)

            actions.append(
                RecoveryAction(
                    action_type="list_similar_files",
                    description=f"Поиск файлов, похожих на '{missing_file}'",
                    parameters={"pattern": missing_file, "fuzzy": True},
                    priority=1,
                )
            )

            actions.append(
                RecoveryAction(
                    action_type="suggest_create_file",
                    description=f"Предложить создать файл '{missing_file}'",
                    parameters={"filename": missing_file},
                    priority=2,
                )
            )

        actions.append(
            RecoveryAction(
                action_type="list_current_directory",
                description="Показать содержимое текущей директории",
                parameters={},
                priority=3,
            )
        )

        return actions

    def _handle_permission_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка ошибок доступа"""
        actions = []

        actions.append(
            RecoveryAction(
                action_type="use_safe_tool",
                description="Использовать безопасный инструмент",
                parameters={"prefer_safe": True},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="check_permissions",
                description="Проверить права доступа к файлу/директории",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_validation_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка ошибок валидации"""
        actions = []

        actions.append(
            RecoveryAction(
                action_type="fix_path_format",
                description="Исправить формат пути",
                parameters={"normalize": True, "escape_special": True},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="validate_input",
                description="Проверить корректность входных данных",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_network_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка сетевых ошибок"""
        actions = []

        actions.append(
            RecoveryAction(
                action_type="retry_request",
                description="Повторить запрос с задержкой",
                parameters={"delay": 2, "max_retries": 3},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="use_alternative_endpoint",
                description="Попробовать альтернативный источник",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_rate_limit_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка ошибок превышения лимитов"""
        actions = []

        # Извлекаем время ожидания из сообщения
        wait_time = self._extract_wait_time(error_message)

        actions.append(
            RecoveryAction(
                action_type="wait_and_retry",
                description=f"Подождать {wait_time} секунд и повторить",
                parameters={"wait_time": wait_time},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="use_alternative_service",
                description="Использовать альтернативный сервис",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_tool_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка ошибок инструментов"""
        actions = []

        if context and context.get("intent"):
            intent = context["intent"]

            actions.append(
                RecoveryAction(
                    action_type="try_alternative_tool",
                    description=f"Попробовать альтернативный инструмент для '{intent}'",
                    parameters={"intent": intent, "exclude_failed": True},
                    priority=1,
                )
            )

        actions.append(
            RecoveryAction(
                action_type="check_tool_availability",
                description="Проверить доступность инструментов",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_syntax_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка синтаксических ошибок"""
        actions = []

        actions.append(
            RecoveryAction(
                action_type="fix_syntax",
                description="Исправить синтаксис команды",
                parameters={"auto_correct": True},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="suggest_correct_format",
                description="Предложить правильный формат",
                parameters={},
                priority=2,
            )
        )

        return actions

    def _handle_unknown_error(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[RecoveryAction]:
        """Обработка неизвестных ошибок"""
        actions = []

        actions.append(
            RecoveryAction(
                action_type="generic_retry",
                description="Повторить операцию",
                parameters={"delay": 1},
                priority=1,
            )
        )

        actions.append(
            RecoveryAction(
                action_type="log_for_analysis",
                description="Записать ошибку для анализа",
                parameters={"error_message": error_message},
                priority=3,
            )
        )

        return actions

    def _extract_wait_time(self, error_message: str) -> int:
        """Извлечение времени ожидания из сообщения об ошибке (оптимизированная версия)"""
        # Ищем числа в сообщении, которые могут быть временем ожидания
        time_match = _TIME_PATTERN.search(error_message)
        if time_match:
            return int(time_match.group(1))

        # Ищем retry_delay
        retry_match = _RETRY_DELAY_PATTERN.search(error_message)
        if retry_match:
            return int(retry_match.group(1))

        return 5  # Значение по умолчанию

    def record_recovery_attempt(
        self, error_type: ErrorType, action: RecoveryAction, success: bool
    ):
        """Запись попытки восстановления для обучения системы"""
        if success:
            self.error_stats["recovered_errors"] += 1

        # Обновляем показатель успешности
        total = self.error_stats["total_errors"]
        recovered = self.error_stats["recovered_errors"]
        self.error_stats["recovery_success_rate"] = (
            (recovered / total * 100) if total > 0 else 0
        )

        if self.debug_mode:
            status = "успешно" if success else "неудачно"
            logger.info(
                f"📊 Восстановление {status}: {action.action_type} для {error_type.value}"
            )

    def get_error_statistics(self) -> Dict[str, Any]:
        """Получение статистики ошибок"""
        return {
            **self.error_stats,
            "most_common_errors": self._get_most_common_errors(),
            "recovery_patterns": self._analyze_recovery_patterns(),
        }

    def _get_most_common_errors(self) -> List[Tuple[str, int]]:
        """Получение наиболее частых ошибок"""
        error_counts = self.error_stats["error_types"]
        return sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    def _analyze_recovery_patterns(self) -> Dict[str, Any]:
        """Анализ паттернов восстановления"""
        return {
            "total_patterns": len(self.error_patterns),
            "cache_size": len(self.recovery_cache),
            "avg_actions_per_error": (
                sum(len(actions) for actions in self.recovery_cache.values())
                / len(self.recovery_cache)
                if self.recovery_cache
                else 0
            ),
        }

    def clear_cache(self):
        """Очистка кэша восстановления"""
        self.recovery_cache.clear()
        logger.info("Кэш системы восстановления очищен")
