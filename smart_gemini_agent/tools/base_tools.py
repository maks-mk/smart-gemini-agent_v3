"""
Базовые классы и утилиты для инструментов
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union, Optional, Tuple
from langchain_core.tools import BaseTool
from pydantic import Field


class SafeToolMixin(ABC):
    """Миксин для безопасных инструментов, работающих только в рабочей директории"""

    def __init__(self, working_directory: Union[str, Path], **kwargs):
        # Миксин: не вызываем super().__init__, чтобы избежать конфликтов MRO
        self.working_directory = Path(working_directory).resolve()

    def _validate_path(
        self, file_path: str
    ) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        Валидация пути для безопасности

        Args:
            file_path: Относительный путь к файлу/директории

        Returns:
            Tuple[is_valid, error_message, resolved_path]
        """
        try:
            # Нормализуем путь и проверяем безопасность
            target_path = Path(self.working_directory) / file_path
            target_path = target_path.resolve()

            # Проверяем, что путь находится внутри рабочей директории
            if not str(target_path).startswith(str(self.working_directory)):
                return (
                    False,
                    f"Попытка доступа к файлу вне рабочей директории: {target_path}",
                    None,
                )

            return True, None, target_path

        except Exception as e:
            return False, f"Ошибка валидации пути {file_path}: {str(e)}", None

    def _format_success(self, message: str) -> str:
        """Форматирование сообщения об успехе"""
        return f"✅ УСПЕХ: {message}"

    def _format_error(self, message: str) -> str:
        """Форматирование сообщения об ошибке"""
        return f"❌ ОШИБКА: {message}"


class FileSystemTool(BaseTool, SafeToolMixin):
    """Базовый класс для инструментов работы с файловой системой"""

    # Храним рабочую директорию как поле Pydantic, исключая из схемы аргументов
    working_directory: Path = Field(exclude=True)

    def __init__(self, working_directory: Union[str, Path], **kwargs):
        # Передаём working_directory в BaseTool, чтобы Pydantic создал поле
        BaseTool.__init__(self, working_directory=working_directory, **kwargs)
        # Нормализуем и резолвим путь после инициализации модели
        self.working_directory = Path(self.working_directory).resolve()

    @abstractmethod
    def _run(self, *args, **kwargs) -> str:
        """Основная логика инструмента"""
        pass

    async def _arun(self, *args, **kwargs) -> str:
        """Асинхронная версия (по умолчанию вызывает синхронную)"""
        return self._run(*args, **kwargs)
