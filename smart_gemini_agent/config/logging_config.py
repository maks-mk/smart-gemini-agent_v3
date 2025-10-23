"""
Настройка логирования для Smart Gemini Agent
"""

import logging
from typing import Optional


class IgnoreSchemaWarnings(logging.Filter):
    """Фильтр для подавления предупреждений о схемах"""

    def filter(self, record):
        ignore_messages = [
            "Key 'additionalProperties' is not supported in schema, ignoring",
            "Key '$schema' is not supported in schema, ignoring",
        ]
        return not any(msg in record.getMessage() for msg in ignore_messages)


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = "ai_agent.log",
    format_string: str = "%(asctime)s - %(levelname)s - %(message)s",
) -> logging.Logger:
    """
    Настройка логирования для агента

    Args:
        level: Уровень логирования
        log_file: Файл для записи логов (None для отключения)
        format_string: Формат сообщений

    Returns:
        Настроенный логгер
    """

    # Создаем обработчики
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    # Базовая настройка
    logging.basicConfig(level=level, format=format_string, handlers=handlers)

    # Применить фильтр ко всем обработчикам
    schema_filter = IgnoreSchemaWarnings()
    for handler in logging.root.handlers:
        handler.addFilter(schema_filter)

    # Дополнительно подавить логгеры MCP и других шумных компонентов
    noisy_loggers = [
        "langchain_mcp_adapters",
        "mcp",
        "jsonschema",
        "langchain_google_genai",
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    return logging.getLogger(__name__)
