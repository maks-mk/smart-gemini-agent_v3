"""
Конфигурация AI-агента для Gemini
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Конфигурация AI-агента для Gemini с загрузкой из файла"""

    filesystem_path: Optional[str] = None  # По умолчанию None
    use_memory: bool = True
    model_name: str = "gemini-2.5-flash"
    model_provider: str = "gemini"  # Новый параметр для указания провайдера модели
    temperature: float = 0.0
    debug_mode: bool = False
    prompt_file: str = "prompt.md"
    mcp_config_file: str = "mcp.json"
    max_context_files: int = 20

    @classmethod
    def from_file(cls, config_file: str = "config.json") -> "AgentConfig":
        """Создание конфигурации из файла"""
        try:
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)

                # Извлекаем настройки агента
                agent_config = config_data.get("agent", {})
                files_config = config_data.get("files", {})
                logging_config = config_data.get("logging", {})

                return cls(
                    model_name=agent_config.get("model_name", "gemini-2.5-flash"),
                    model_provider=agent_config.get(
                        "model_provider", "gemini"
                    ),  # Новый параметр
                    temperature=agent_config.get("temperature", 0.0),
                    use_memory=agent_config.get("use_memory", True),
                    max_context_files=agent_config.get("max_context_files", 20),
                    debug_mode=bool(
                        logging_config.get("debug_mode", logging_config.get("debug", False))
                    ),
                    prompt_file=files_config.get("prompt_file", "prompt.md"),
                    mcp_config_file=files_config.get("mcp_config_file", "mcp.json"),
                )
            else:
                logger.info(
                    f"Файл конфигурации {config_file} не найден, используются настройки по умолчанию"
                )
                return cls()
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации из {config_file}: {e}")
            return cls()

    def __post_init__(self):
        """Автоматическая установка рабочей директории при инициализации"""
        if self.filesystem_path is None:
            self.filesystem_path = os.getcwd()
            logger.info(
                f"Рабочая директория не указана, используется текущая: {self.filesystem_path}"
            )

        # Нормализация пути (добавление завершающего слеша)
        if not self.filesystem_path.endswith(os.sep):
            self.filesystem_path += os.sep

    def validate(self) -> None:
        """Простая валидация"""
        if not self.filesystem_path or not os.path.exists(self.filesystem_path):
            raise ValueError(f"Путь не существует: {self.filesystem_path}")

        # Проверяем API ключ в зависимости от провайдера
        if self.model_provider == "gemini" and not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("Отсутствует переменная окружения: GOOGLE_API_KEY")
        elif self.model_provider == "openrouter" and not os.getenv(
            "OPENROUTER_API_KEY"
        ):
            raise ValueError("Отсутствует переменная окружения: OPENROUTER_API_KEY")

    def get_mcp_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации MCP серверов из файла"""
        mcp_config_path = self.mcp_config_file

        try:
            if not os.path.exists(mcp_config_path):
                logger.warning(
                    f"Файл {mcp_config_path} не найден, используется конфигурация по умолчанию"
                )
                return self._get_default_mcp_config()

            with open(mcp_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Заменяем плейсхолдеры во всей конфигурации
            # Нормализуем путь для JSON (используем прямые слеши)
            if self.filesystem_path:
                normalized_path = self.filesystem_path.replace("\\", "/")
            else:
                normalized_path = os.getcwd().replace("\\", "/")
            config_str = json.dumps(config)
            config_str = config_str.replace("{filesystem_path}", normalized_path)
            config = json.loads(config_str)

            # Фильтруем только включенные серверы
            enabled_config = self._filter_enabled_servers(config)

            all_servers = list(config.keys())
            enabled_servers = list(enabled_config.keys())
            disabled_servers = [s for s in all_servers if s not in enabled_servers]

            logger.info(f"✅ Загружена конфигурация MCP из {mcp_config_path}")
            logger.info(f"📊 Всего серверов: {len(all_servers)}")
            logger.info(f"✅ Включенные серверы: {enabled_servers}")
            if disabled_servers:
                logger.info(f"❌ Отключенные серверы: {disabled_servers}")

            return enabled_config

        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга {mcp_config_path}: {e}")
            logger.error(f"Проблемный путь: {self.filesystem_path}")
            logger.info("Используется конфигурация по умолчанию")
            return self._get_default_mcp_config()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {mcp_config_path}: {e}")
            return self._get_default_mcp_config()

    def _filter_enabled_servers(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Фильтрует только включенные MCP серверы"""
        enabled_config = {}

        for server_name, server_config in config.items():
            # Проверяем параметр enabled (по умолчанию True, если не указан)
            is_enabled = server_config.get("enabled", True)

            if is_enabled:
                # Создаем копию конфигурации без параметра enabled для MCP клиента
                clean_config = {
                    k: v for k, v in server_config.items() if k != "enabled"
                }
                enabled_config[server_name] = clean_config
            else:
                logger.debug(f"Сервер {server_name} отключен (enabled: false)")

        return enabled_config

    def _get_default_mcp_config(self) -> Dict[str, Any]:
        """Конфигурация MCP серверов по умолчанию"""
        return {
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    self.filesystem_path,
                ],
                "transport": "stdio",
                "enabled": True,
            },
            "duckduckgo": {
                "command": "uvx",
                "args": ["duckduckgo-mcp-server"],
                "transport": "stdio",
                "enabled": True,
            },
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "transport": "stdio",
                "enabled": True,
            },
        }
