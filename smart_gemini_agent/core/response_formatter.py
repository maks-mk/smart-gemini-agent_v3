"""
Форматтер ответов для Smart Gemini Agent
"""

import re
import ast
import logging
from typing import Optional, Any, List
from ..utils.file_formatters import FileFormatter

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Класс для форматирования ответов агента"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.file_formatter = FileFormatter()
        # Предкомпилированные паттерны для скорости
        self._json_codeblock_re = re.compile(
            r"```json\n(\{[\s\S]*?\})\n```", re.IGNORECASE
        )
        self._dir_item_re = re.compile(r"(\[(FILE|DIR)\])\s*([^\s\[\]]+)")
        self._patterns: List[re.Pattern] = [
            re.compile(r"\[Содержимое файла ([^']+):', '([^']+)'\]", re.DOTALL),
            re.compile(r"\[Файл ([^']+) содержит[^']*:', '([^']+)'\]", re.DOTALL),
            re.compile(r"\[([^']*файл[^']*)', '([^']+)'\]", re.DOTALL | re.IGNORECASE),
            re.compile(r"\[([^,]+), '([^']+)'\]", re.DOTALL),
            re.compile(r'\["([^"]*файл[^"]*)", "([^"]+)"\]', re.DOTALL | re.IGNORECASE),
            re.compile(
                r"Содержимое файла ([^:]+):\s*(.+?)(?=\n\n|\Z)",
                re.DOTALL | re.IGNORECASE,
            ),
        ]

    def improve_file_content_formatting(self, response: str) -> str:
        """
        Улучшает форматирование содержимого файлов в ответе

        Args:
            response: Исходный ответ агента

        Returns:
            Отформатированный ответ
        """
        if self.debug_mode:
            logger.debug(f"Исходный ответ для форматирования: {response[:200]}...")

        # Нормализация: если ответ обёрнут в словарь вида {'type': 'text', 'text': '...'} — извлечь текст
        unwrapped = self._extract_wrapped_text(response)
        if unwrapped is not None:
            response = unwrapped

        # Попытка обработки как JSON
        formatted_json = self._handle_json_response(response)
        if formatted_json:
            return formatted_json

        # Новая специальная обработка для вывода списка директории
        if "Содержимое текущей рабочей директории" in response or re.search(
            r"\[(FILE|DIR)\]", response
        ):
            formatted = self._format_list_directory_response(response)
            # Используем отформатированный ответ, даже если он None, чтобы передать дальше
            if formatted is not None:
                return formatted

        # Специальная обработка для ответов-массивов
        if response.startswith("[") and response.endswith("]"):
            formatted = self._handle_array_response(response)
            if formatted:
                return formatted

        # Проверяем, не является ли ответ уже правильно отформатированным
        if self._is_already_formatted(response):
            if self.debug_mode:
                logger.debug("Ответ уже правильно отформатирован")
            return response

        # Обработка различных паттернов
        formatted = self._handle_pattern_matching(response)
        if formatted:
            return formatted

        if self.debug_mode:
            logger.debug("Паттерны не найдены, возвращаем исходный ответ")
        return response

    def _handle_json_response(self, response: str) -> Optional[str]:
        """Обработка ответов в формате JSON."""
        try:
            # Ищем JSON в тексте
            match = self._json_codeblock_re.search(response)
            if not match:
                return None

            raw = match.group(1)
            # Сначала пробуем как JSON
            import json

            try:
                json_data = json.loads(raw)
            except Exception:
                # Фолбек на python-подобный литерал
                json_data = ast.literal_eval(raw)

            if (
                isinstance(json_data, dict)
                and "file_path" in json_data
                and "content" in json_data
            ):
                filename = json_data["file_path"]
                content = json_data["content"]
                language = json_data.get(
                    "language", self.file_formatter.get_language_by_filename(filename)
                )

                # Автоматическое форматирование содержимого
                content = self.file_formatter.format_content(
                    content, language, filename
                )

                formatted_response = (
                    f"Содержимое файла `{filename}`:\n\n```{language}\n{content}\n```"
                )

                if self.debug_mode:
                    logger.debug(
                        f"Успешно отформатирован ответ-JSON для файла {filename}"
                    )

                return formatted_response

        except (ValueError, SyntaxError, KeyError) as e:
            if self.debug_mode:
                logger.debug(f"Не удалось распарсить JSON: {e}")

        return None

    def _extract_wrapped_text(self, response: str) -> Optional[str]:
        """Если строка выглядит как словарь c ключом 'text', извлечь и разэкранировать текст."""
        try:
            text = response.strip()
            # Быстрая проверка
            if not (text.startswith("{") and ("text" in text)):
                return None
            # Пытаемся безопасно распарсить Python-подобный литерал
            data = ast.literal_eval(text)
            if (
                isinstance(data, dict)
                and "text" in data
                and isinstance(data["text"], str)
            ):
                extracted = data["text"]
                # Разэкранируем \n и кавычки
                extracted = (
                    extracted.replace("\\n", "\n")
                    .replace('\\"', '"')
                    .replace("\\'", "'")
                )
                return extracted
        except Exception:
            return None
        return None

    def _format_list_directory_response(self, response: str) -> Optional[str]:
        """Форматирует вывод списка директории в красивый markdown-список."""
        try:
            header = "Содержимое текущей рабочей директории:"
            # Ищем контент после заголовка или с начала строки
            content_part = response.split(header, 1)[-1]

            # Используем regex для поиска всех тегов [FILE] и [DIR]
            items = self._dir_item_re.findall(content_part)

            if not items:
                # Если обнаружены маскированные элементы с '**', подавим шум и оставим только заголовок
                if "**" in content_part:
                    return header
                return response  # Если не нашли, возвращаем как есть

            output_lines = [header]
            for tag, _, name in items:
                emoji = "📄" if tag == "[FILE]" else "📁"
                output_lines.append(f"{emoji} {name}")

            return "\n".join(output_lines)
        except Exception as e:
            if self.debug_mode:
                logger.error(f"Ошибка форматирования списка директории: {e}")
            return response  # В случае ошибки возвращаем исходный ответ

    def _handle_array_response(self, response: str) -> Optional[str]:
        """Обработка ответов в формате массива"""
        if self.debug_mode:
            logger.debug("Обнаружен ответ в формате массива")

        try:
            # Пробуем безопасно распарсить массив
            parsed = ast.literal_eval(response)
            if isinstance(parsed, list) and len(parsed) >= 2:
                description = str(parsed[0])
                content = str(parsed[1])

                # Извлекаем имя файла из описания
                filename_match = re.search(r"([^\s]+\.[a-zA-Z0-9]+)", description)
                if filename_match:
                    filename = filename_match.group(1)

                    # Обрабатываем содержимое
                    if content.startswith("```") and content.endswith("```"):
                        # Содержимое уже в markdown формате
                        lines = content.strip("`").split("\n")
                        if lines and lines[0]:  # Первая строка - язык
                            language = lines[0]
                            actual_content = "\n".join(lines[1:])
                        else:
                            language = self.file_formatter.get_language_by_filename(
                                filename
                            )
                            actual_content = "\n".join(lines[1:])
                    else:
                        language = self.file_formatter.get_language_by_filename(
                            filename
                        )
                        actual_content = content

                    # Автоматическое форматирование содержимого
                    actual_content = self.file_formatter.format_content(
                        actual_content, language, filename
                    )

                    formatted_response = f"Содержимое файла `{filename}`:\n\n```{language}\n{actual_content}\n```"

                    if self.debug_mode:
                        logger.debug(
                            f"Успешно отформатирован ответ-массив для файла {filename}"
                        )

                    return formatted_response

        except (ValueError, SyntaxError) as e:
            if self.debug_mode:
                logger.debug(f"Не удалось распарсить массив: {e}")

        return None

    def _is_already_formatted(self, response: str) -> bool:
        """Проверка, отформатирован ли уже ответ"""
        # Условие немного ослаблено, чтобы не мешать новому формату списка
        return "```" in response and response.count("\n") > 2

    def _handle_pattern_matching(self, response: str) -> Optional[str]:
        """Обработка различных паттернов в ответе"""
        for i, pattern in enumerate(self._patterns):
            match = pattern.search(response)
            if match:
                if self.debug_mode:
                    logger.debug(f"Найдено совпадение с паттерном {i}: {pattern}")

                first_part = match.group(1).strip()
                content = match.group(2).strip()

                # Извлекаем имя файла из первой части
                filename = self._extract_filename(first_part, response)

                # Очищаем содержимое
                content = self._clean_content(content)

                # Если содержимое пустое или слишком короткое, возвращаем исходный ответ
                if len(content.strip()) < 3:
                    if self.debug_mode:
                        logger.debug(
                            "Содержимое слишком короткое, возвращаем исходный ответ"
                        )
                    return None

                # Определяем язык и форматируем
                language = self.file_formatter.get_language_by_filename(filename)
                content = self.file_formatter.format_content(
                    content, language, filename
                )

                # Создаем правильно отформатированный ответ
                formatted_response = (
                    f"Содержимое файла `{filename}`:\n\n```{language}\n{content}\n```"
                )

                if self.debug_mode:
                    logger.debug(f"Создан отформатированный ответ для файла {filename}")

                return formatted_response

        # Проверяем, есть ли в ответе упоминание файла без правильного форматирования
        if re.search(
            r"(файл|file).*\\.(txt|py|js|json|md|yml|xml|csv)", response, re.IGNORECASE
        ):
            if self.debug_mode:
                logger.debug(
                    "Найдено упоминание файла, но не удалось извлечь содержимое"
                )

        return None

    def _extract_filename(self, first_part: str, full_response: str) -> str:
        """Извлечение имени файла из текста"""
        # Извлекаем имя файла из первой части
        filename_match = re.search(r"([^\s]+\.[a-zA-Z0-9]+)", first_part)
        if filename_match:
            return filename_match.group(1)

        # Пробуем найти имя файла в полном ответе
        filename_in_response = re.search(r"([^\s]+\.[a-zA-Z0-9]+)", full_response)
        return filename_in_response.group(1) if filename_in_response else "file.txt"

    def _clean_content(self, content: str) -> str:
        """Очистка содержимого от escape-символов и лишних кавычек"""
        content = content.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
        content = content.strip("\"'")
        return content

    def normalize_text(self, content: Any) -> str:
        """Унифицированная нормализация произвольного контента в текст.
        - dict с ключом 'text' -> берём text
        - list -> конкатенируем элементы, рекурсивно нормализуя
        - строки с экранированными символами -> разэкранируем базовые
        """
        try:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                txt = content["text"]
            elif isinstance(content, list):
                parts = [self.normalize_text(x) for x in content]
                txt = "\n".join(parts)
            else:
                txt = str(content)
            return txt.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
        except Exception:
            return str(content)

    def format_error_message(self, error: str) -> str:
        """Форматирование сообщения об ошибке"""
        return f"❌ {error}"

    def format_success_message(self, message: str) -> str:
        """Форматирование сообщения об успехе"""
        return f"✅ {message}"

    def format_info_message(self, message: str) -> str:
        """Форматирование информационного сообщения"""
        return f"ℹ️ {message}"

    def format_warning_message(self, message: str) -> str:
        """Форматирование предупреждения"""
        return f"⚠️ {message}"
