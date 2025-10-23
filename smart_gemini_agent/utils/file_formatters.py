"""
Утилиты для форматирования файлов
"""

import json
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


class FileFormatter:
    """Класс для форматирования содержимого файлов"""

    @staticmethod
    @lru_cache(maxsize=256)
    def get_language_by_filename(filename: str) -> str:
        """Определяет язык для подсветки синтаксиса по имени файла (кешируется)"""
        extension = filename.lower().split(".")[-1] if "." in filename else ""

        language_map = {
            "json": "json",
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "md": "markdown",
            "yml": "yaml",
            "yaml": "yaml",
            "xml": "xml",
            "html": "html",
            "css": "css",
            "sql": "sql",
            "sh": "bash",
            "ps1": "powershell",
            "csv": "csv",
            "txt": "text",
            "log": "text",
            "ini": "ini",
            "cfg": "ini",
            "conf": "text",
            "env": "bash",
        }

        return language_map.get(extension, "text")

    @staticmethod
    def format_content(content: str, language: str, filename: str) -> str:
        """Автоматическое форматирование содержимого файлов"""
        if not content or not content.strip():
            return content

        try:
            if language == "json":
                return FileFormatter._format_json(content, filename)
            elif language == "xml":
                return FileFormatter._format_xml(content, filename)
            elif language in ["yaml", "yml"]:
                return FileFormatter._format_yaml(content, filename)

        except Exception as e:
            logger.debug(f"Не удалось отформатировать {language} файл {filename}: {e}")

        # Если форматирование не удалось или не нужно, возвращаем как есть
        return content

    @staticmethod
    def _format_json(content: str, filename: str) -> str:
        """Форматирование JSON"""
        parsed_json = json.loads(content)
        formatted_content = json.dumps(parsed_json, indent=2, ensure_ascii=False)
        logger.debug(f"JSON файл {filename} автоматически отформатирован")
        return formatted_content

    @staticmethod
    def _format_xml(content: str, filename: str) -> str:
        """Форматирование XML"""
        try:
            import xml.dom.minidom

            dom = xml.dom.minidom.parseString(content)
            formatted_content = dom.toprettyxml(indent="  ")
            # Убираем лишние пустые строки
            lines = [line for line in formatted_content.split("\n") if line.strip()]
            formatted_content = "\n".join(lines)
            logger.debug(f"XML файл {filename} автоматически отформатирован")
            return formatted_content
        except Exception:
            return content  # Если не удалось, оставляем как есть

    @staticmethod
    def _format_yaml(content: str, filename: str) -> str:
        """Базовое форматирование YAML"""
        lines = content.split("\n")
        formatted_lines = []
        indent_level = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted_lines.append("")
                continue

            # Простое форматирование YAML (базовое)
            if ":" in stripped and not stripped.startswith("-"):
                formatted_lines.append("  " * indent_level + stripped)
                if not stripped.endswith(":"):
                    indent_level = max(0, indent_level)
            else:
                formatted_lines.append("  " * indent_level + stripped)

        if len(formatted_lines) != len(lines):  # Если что-то изменилось
            logger.debug(f"YAML файл {filename} автоматически отформатирован")
            return "\n".join(formatted_lines)

        return content
