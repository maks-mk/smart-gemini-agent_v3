"""
Анализатор и категоризатор инструментов с оптимизированной производительностью
"""

import re
import logging
from typing import Dict, List, Pattern
from functools import lru_cache
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolAnalyzer:
    """Класс для анализа и категоризации инструментов"""

    def __init__(self):
        self.tools_map: Dict[str, List[BaseTool]] = {}
        
        # Предкомпилированные паттерны для производительности
        self._compiled_patterns: Dict[str, List[Pattern]] = {}
        self.categorization_patterns = {
            "read_file": [
                r"^(read|get|cat|show|view)_file$",
                r"^read_.*_file$",
                r"^get_file_.*$",
            ],
            "write_file": [
                r"^(write|create|save|put)_file$",
                r"^(write|create)_.*_file$",
                r"^edit_file$",
            ],
            "list_directory": [
                r"^list_.*",
                r"^ls$",
                r"^dir$",
                r".*(directory|dir|folder).*list.*",
                r".*list.*(directory|dir|folder).*",
                r"^directory_tree$",
            ],
            "create_directory": [
                r"^create_.*(directory|dir|folder)$",
                r"^mkdir$",
                r"^make_.*dir$",
            ],
            "delete_file": [r"^(delete|remove|rm|unlink)_.*", r"^safe_delete_.*"],
            "move_file": [r"^(move|mv|rename)_.*"],
            "search": [r"^(search|find|grep)_files?$", r"^search$"],
            "web_search": [r".*(web|internet|duckduckgo|google).*search.*"],
            "fetch_url": [r"^(fetch|download|get)_url$", r".*fetch.*"],
        }
        
        # Компилируем все паттерны при инициализации
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Предкомпиляция регулярных выражений для производительности"""
        for category, patterns in self.categorization_patterns.items():
            self._compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
        logger.debug(f"Скомпилировано {sum(len(p) for p in self._compiled_patterns.values())} регулярных выражений")

    def analyze_tools(self, tools: List[BaseTool]) -> Dict[str, List[BaseTool]]:
        """
        Универсальный анализ и категоризация доступных инструментов

        Args:
            tools: Список инструментов для анализа

        Returns:
            Словарь с категоризированными инструментами
        """
        # Инициализируем базовые категории
        self.tools_map = {
            "read_file": [],
            "write_file": [],
            "list_directory": [],
            "create_directory": [],
            "delete_file": [],
            "move_file": [],
            "search": [],
            "web_search": [],
            "fetch_url": [],
            "other": [],
        }

        # Категоризируем каждый инструмент
        for tool in tools:
            name = tool.name.lower()
            description = (
                getattr(tool, "description", "").lower()
                if hasattr(tool, "description")
                else ""
            )

            categorized = False

            # Проверяем каждую категорию (используем предкомпилированные паттерны)
            for category, compiled_patterns in self._compiled_patterns.items():
                for pattern in compiled_patterns:
                    if pattern.search(name) or (description and pattern.search(description)):
                        if tool not in self.tools_map[category]:
                            self.tools_map[category].append(tool)
                        categorized = True
                        break
                if categorized:
                    break

            # Если инструмент не попал ни в одну категорию
            if not categorized:
                if tool not in self.tools_map["other"]:
                    self.tools_map["other"].append(tool)

        # Логируем результаты категоризации
        logger.info("Автоматическая категоризация инструментов:")
        for category, category_tools in self.tools_map.items():
            if category_tools:
                logger.info(f"  {category}: {[t.name for t in category_tools]}")

        # Предупреждение если есть много неопознанных инструментов
        if len(self.tools_map["other"]) > len(tools) * 0.3:
            logger.warning(
                f"Много инструментов в категории 'other' ({len(self.tools_map['other'])}). "
                f"Возможно, нужно обновить паттерны категоризации."
            )

        return self.tools_map

    def generate_tools_description(self) -> str:
        """Генерация детального описания инструментов"""
        descriptions = []

        # Автоматическое определение категорий на основе доступных инструментов
        category_names = {
            "read_file": "ЧТЕНИЕ ФАЙЛОВ",
            "write_file": "СОЗДАНИЕ/ЗАПИСЬ ФАЙЛОВ",
            "list_directory": "ПРОСМОТР ДИРЕКТОРИЙ",
            "create_directory": "СОЗДАНИЕ ПАПОК",
            "delete_file": "УДАЛЕНИЕ ФАЙЛОВ/ПАПОК",
            "move_file": "ПЕРЕМЕЩЕНИЕ/ПЕРЕИМЕНОВАНИЕ",
            "search": "ПОИСК ФАЙЛОВ",
            "web_search": "ВЕБ-ПОИСК",
            "fetch_url": "ЗАГРУЗКА ИЗ ИНТЕРНЕТА",
            "other": "ДРУГИЕ ИНСТРУМЕНТЫ",
        }

        # Показываем только категории с доступными инструментами
        for category, tools in self.tools_map.items():
            if tools:  # Показываем только непустые категории
                category_desc = category_names.get(
                    category, category.replace("_", " ").upper()
                )
                descriptions.append(f"\n{category_desc}:")

                for tool in tools:
                    tool_desc = self.get_tool_description(tool)
                    descriptions.append(f"  • {tool.name}: {tool_desc}")

        # Если нет инструментов вообще
        if not descriptions:
            descriptions.append("\nИнструменты не загружены или недоступны.")

        return "\n".join(descriptions)

    def get_tool_description(self, tool: BaseTool) -> str:
        """Получение описания инструмента с автоматическим анализом"""
        # Сначала пробуем использовать оригинальное описание
        if hasattr(tool, "description") and tool.description:
            desc = tool.description.strip()
            if desc:
                return desc[:150] + ("..." if len(desc) > 150 else "")

        # Автоматическое определение функции на основе названия
        name = tool.name.lower()

        # Паттерны для определения функций инструментов
        patterns = {
            # Чтение файлов
            r"(read|get|cat|show|view).*file": "Читает содержимое файла",
            r"(read|get)_.*": "Читает данные",
            # Запись файлов
            r"(write|create|save|put).*file": "Создает или записывает файл",
            r"(write|create)_.*": "Создает или записывает данные",
            # Работа с директориями
            r"(list|ls|dir).*": "Показывает содержимое директории",
            r".*(directory|dir|folder).*list": "Показывает содержимое директории",
            r"create.*(directory|dir|folder)": "Создает новую папку",
            r"mkdir": "Создает новую папку",
            # Удаление
            r"(delete|remove|rm|unlink).*": "Удаляет файл или папку",
            r"safe_delete_file": "Безопасно удаляет файлы только внутри рабочей директории",
            r"safe_delete_directory": "Безопасно удаляет директории только внутри рабочей директории",
            # Перемещение
            r"(move|mv|rename).*": "Перемещает или переименовывает файл",
            # Поиск
            r"(search|find|grep).*file": "Ищет файлы по критериям",
            r"(search|find).*": "Выполняет поиск",
            # Веб-функции
            r".*(web|internet|duckduckgo|google).*search": "Поиск информации в интернете",
            r"(fetch|download|get).*url": "Загружает данные по URL",
            r"(http|https|url).*": "Работает с веб-ресурсами",
            # Системные команды
            r"(shell|exec|run|command).*": "Выполняет системные команды",
            # Специальные функции
            r".*server.*": "MCP сервер инструмент",
            r".*mcp.*": "Model Context Protocol инструмент",
        }

        # Проверяем паттерны
        for pattern, description in patterns.items():
            if re.search(pattern, name):
                return description

        # Если ничего не подошло, возвращаем общее описание
        return f"Инструмент: {tool.name}"

    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """Получить инструменты по категории"""
        return self.tools_map.get(category, [])

    def get_all_categories(self) -> List[str]:
        """Получить список всех категорий"""
        return list(self.tools_map.keys())

    def get_tools_count_by_category(self) -> Dict[str, int]:
        """Получить количество инструментов по категориям"""
        return {category: len(tools) for category, tools in self.tools_map.items()}
