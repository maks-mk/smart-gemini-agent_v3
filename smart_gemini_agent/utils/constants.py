"""
Константы проекта Smart Gemini Agent v5.0
Централизованное хранение всех магических чисел и строк
"""

import re

# === Константы повторов и таймаутов ===
MAX_RETRY_ATTEMPTS = 2
DEFAULT_THREAD_ID = "default"
MAX_RECOVERY_SUGGESTIONS = 3
RATE_LIMIT_HTTP_CODE = "429"
MAX_TOOL_REPEATS = 10  # Максимальное количество повторов одного инструмента
DEFAULT_REQUEST_TIMEOUT = 300.0  # Таймаут запроса по умолчанию (секунды)
DEFAULT_TOOL_TIMEOUT = 300.0  # Таймаут инструмента по умолчанию (секунды)

# === Константы логирования ===
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "ai_agent.log"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# === Константы конфигурации ===
DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_MEMORY_PATH = "./agent_memory"
DEFAULT_TRACES_DIR = "./traces"
DEFAULT_MAX_CONTEXT_FILES = 20
DEFAULT_TEMPERATURE = 0.1

# === Версия приложения ===
APP_VERSION = "5.0"
APP_NAME = "Smart Gemini Agent"

# === Предкомпилированные регулярные выражения ===
# Паттерн для извлечения задержки retry из текста ошибки
RETRY_DELAY_PATTERN = re.compile(r"retry_delay\s*{\s*seconds:\s*(\d+)")

# Паттерны для обнаружения ошибок
RATE_LIMIT_PATTERN = re.compile(r"(429|ResourceExhausted)", re.IGNORECASE)
AUTH_ERROR_PATTERN = re.compile(r"(401|403|Unauthorized|Forbidden)", re.IGNORECASE)
TIMEOUT_PATTERN = re.compile(r"(timeout|timed out)", re.IGNORECASE)
