"""
Менеджер промптов для Smart Gemini Agent
"""

import os
import logging
from typing import Optional
from ..config.agent_config import AgentConfig
from ..tools.tool_analyzer import ToolAnalyzer
from ..utils.config_updater import ConfigUpdater

logger = logging.getLogger(__name__)


class PromptManager:
    """Класс для управления системными промптами"""

    def __init__(
        self, config: AgentConfig, tool_analyzer: Optional[ToolAnalyzer] = None
    ):
        self.config = config
        self.tool_analyzer = tool_analyzer

        logger.info(f"Инициализирован менеджер промптов с файлом: {config.prompt_file}")

    def get_system_prompt(self) -> str:
        """Получение системного промпта"""
        return self._load_prompt_from_file()

    def _load_prompt_from_file(self) -> str:
        """Загрузка промпта из файла с подстановкой переменных"""
        prompt_file = self.config.prompt_file

        try:
            if not os.path.exists(prompt_file):
                logger.warning(
                    f"Файл {prompt_file} не найден, используется промпт по умолчанию"
                )
                return self._get_default_prompt()

            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            # Подставляем переменные безопасно
            tools_description = self._generate_tools_description()
            filesystem_path = self.config.filesystem_path or os.getcwd()

            prompt = prompt_template.replace("{filesystem_path}", filesystem_path)
            prompt = prompt.replace("{tools_description}", tools_description)

            logger.info(f"✅ Загружен промпт из {prompt_file}")
            return prompt

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки промпта из {prompt_file}: {e}")
            logger.info("Используется промпт по умолчанию")
            return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Универсальный промпт по умолчанию на случай ошибки загрузки"""
        tools_description = self._generate_tools_description()
        filesystem_path = self.config.filesystem_path or os.getcwd()

        return f"""Ты умный AI-ассистент с доступом к различным инструментам.

РАБОЧАЯ ДИРЕКТОРИЯ: {filesystem_path}
Все файловые операции выполняются относительно этой директории.

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
{tools_description}

ПРАВИЛА РАБОТЫ:
1. Анализируй запрос пользователя и определяй нужную операцию
2. Используй ТОЛЬКО предоставленные инструменты из списка выше
3. Автоматически выбирай подходящий инструмент на основе его названия и описания
4. По умолчанию используй относительные пути; абсолютные указывай только если это требуется (например, для Excel файлов)
5. При создании файлов с содержимым используй соответствующие параметры
6. Если путь не указан явно, работай в текущей рабочей директории
7. Адаптируйся к доступным инструментам - если нет конкретного инструмента, найди альтернативу
8. НЕ ВЫДУМЫВАЙ несуществующие инструменты или команды

ФОРМАТ ОТВЕТА:
- Кратко подтверди выполненное действие
- При ошибках объясни причину и предложи решение
- Для сложных операций опиши что делаешь пошагово"""

    def _generate_tools_description(self) -> str:
        """Генерация описания инструментов"""
        if self.tool_analyzer:
            return self.tool_analyzer.generate_tools_description()
        else:
            return "Инструменты не загружены или недоступны."

    def update_tool_analyzer(self, tool_analyzer: ToolAnalyzer):
        """Обновление анализатора инструментов"""
        self.tool_analyzer = tool_analyzer

    def reload_prompt(self) -> str:
        """Перезагрузка промпта из файла"""
        logger.info("Перезагрузка промпта...")
        return self._load_prompt_from_file()

    def validate_prompt_file(self) -> bool:
        """Проверка существования файла промпта"""
        return os.path.exists(self.config.prompt_file)

    def get_prompt_file_path(self) -> str:
        """Получение пути к файлу промпта"""
        return self.config.prompt_file

    def update_prompt_file(self, new_prompt_file: str) -> bool:
        """Обновление пути к файлу промпта"""
        if os.path.exists(new_prompt_file):
            self.config.prompt_file = new_prompt_file
            logger.info(f"Обновлен файл промпта: {new_prompt_file}")
            return True
        else:
            logger.error(f"Файл промпта не найден: {new_prompt_file}")
            return False

    def get_available_prompts(self) -> list[str]:
        """Получение списка доступных файлов промптов"""
        updater = ConfigUpdater()
        return updater.get_available_prompts()
