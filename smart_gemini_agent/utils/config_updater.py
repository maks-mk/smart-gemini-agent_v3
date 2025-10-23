"""
Утилита для обновления конфигурации агента
"""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigUpdater:
    """Класс для динамического обновления конфигурации"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self._config_data: Optional[Dict[str, Any]] = None
        self._load_config()

    def _load_config(self) -> None:
        """Загрузка конфигурации из файла"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self._config_data = json.load(f)
                logger.info(f"Загружена конфигурация из {self.config_file}")
            else:
                logger.error(f"Файл конфигурации {self.config_file} не найден")
                self._config_data = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            self._config_data = {}

    def update_prompt_file(self, new_prompt_file: str) -> bool:
        """Обновление файла промпта в конфигурации"""
        if not os.path.exists(new_prompt_file):
            logger.error(f"Файл промпта не найден: {new_prompt_file}")
            return False

        if not self._config_data:
            logger.error("Конфигурация не загружена")
            return False

        # Обновляем конфигурацию
        if "files" not in self._config_data:
            self._config_data["files"] = {}

        old_prompt = self._config_data["files"].get("prompt_file", "не указан")
        self._config_data["files"]["prompt_file"] = new_prompt_file

        # Сохраняем изменения
        if self._save_config():
            logger.info(f"Файл промпта обновлен: {old_prompt} → {new_prompt_file}")
            return True

        return False

    def get_current_prompt_file(self) -> Optional[str]:
        """Получение текущего файла промпта"""
        if self._config_data and "files" in self._config_data:
            return self._config_data["files"].get("prompt_file")
        return None

    def get_available_prompts(self) -> list[str]:
        """Получение списка доступных файлов промптов"""
        prompt_files = []
        for file in os.listdir("."):
            if file.startswith("prompt") and file.endswith(".md"):
                prompt_files.append(file)
        return sorted(prompt_files)

    def update_config_value(self, section: str, key: str, value: Any) -> bool:
        """Обновление произвольного значения в конфигурации"""
        if not self._config_data:
            logger.error("Конфигурация не загружена")
            return False

        if section not in self._config_data:
            self._config_data[section] = {}

        old_value = self._config_data[section].get(key, "не указано")
        self._config_data[section][key] = value

        if self._save_config():
            logger.info(f"Обновлено {section}.{key}: {old_value} → {value}")
            return True

        return False

    def _save_config(self) -> bool:
        """Сохранение конфигурации в файл"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._config_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Конфигурация сохранена в {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")
            return False

    def get_config_summary(self) -> Dict[str, Any]:
        """Получение сводки текущей конфигурации"""
        if not self._config_data:
            return {"error": "Конфигурация не загружена"}

        return {
            "config_file": self.config_file,
            "current_prompt": self.get_current_prompt_file(),
            "available_prompts": self.get_available_prompts(),
            "sections": list(self._config_data.keys()),
            "agent_model": self._config_data.get("agent", {}).get(
                "model_name", "не указан"
            ),
            "logging_level": self._config_data.get("logging", {}).get(
                "level", "не указан"
            ),
        }


def switch_prompt(new_prompt_file: str, config_file: str = "config.json") -> bool:
    """Быстрая функция для переключения промпта"""
    updater = ConfigUpdater(config_file)
    return updater.update_prompt_file(new_prompt_file)


def list_available_prompts() -> list[str]:
    """Быстрая функция для получения списка промптов"""
    updater = ConfigUpdater()
    return updater.get_available_prompts()
