"""
Безопасные инструменты для удаления файлов и директорий
"""

import shutil
from pathlib import Path
from typing import Type
from pydantic import BaseModel, Field
from .base_tools import FileSystemTool


class DeleteFileInput(BaseModel):
    """Входные параметры для инструмента удаления файлов"""

    file_path: str = Field(description="Относительный путь к файлу для удаления")


class SafeDeleteFileTool(FileSystemTool):
    """Безопасный инструмент для удаления файлов только внутри рабочей директории"""

    name: str = "safe_delete_file"
    description: str = (
        "Безопасно удаляет файл только внутри рабочей директории. Принимает относительный путь к файлу."
    )
    args_schema: Type[BaseModel] = DeleteFileInput

    def _run(self, file_path: str) -> str:
        """Выполняет удаление файла"""
        try:
            # Валидация пути
            is_valid, error_msg, target_path = self._validate_path(file_path)
            if not is_valid:
                return self._format_error(error_msg or "Недопустимый путь")

            if target_path is None:
                return self._format_error("Внутренняя ошибка валидации пути")

            # Проверяем существование файла
            if not target_path.exists():
                return self._format_error(f"Файл не найден: {file_path}")

            # Проверяем, что это файл, а не директория
            if target_path.is_dir():
                return self._format_error(
                    f"{file_path} является директорией. Используйте инструмент для удаления директорий."
                )

            # Удаляем файл
            target_path.unlink()

            return self._format_success(f"Файл {file_path} успешно удален")

        except PermissionError:
            return self._format_error(f"Нет прав для удаления файла {file_path}")
        except Exception as e:
            return self._format_error(
                f"Не удалось удалить файл {file_path}. Причина: {str(e)}"
            )

    async def _arun(self, file_path: str) -> str:
        """Асинхронная версия удаления файла"""
        return self._run(file_path)


class DeleteDirectoryInput(BaseModel):
    """Входные параметры для инструмента удаления директорий"""

    dir_path: str = Field(description="Относительный путь к директории для удаления")
    recursive: bool = Field(
        default=False, description="Удалить директорию рекурсивно (со всем содержимым)"
    )


class SafeDeleteDirectoryTool(FileSystemTool):
    """Безопасный инструмент для удаления директорий только внутри рабочей директории"""

    name: str = "safe_delete_directory"
    description: str = (
        "Безопасно удаляет директорию только внутри рабочей директории. Может удалять рекурсивно."
    )
    args_schema: Type[BaseModel] = DeleteDirectoryInput

    def _run(self, dir_path: str, recursive: bool = False) -> str:
        """Выполняет удаление директории"""
        try:
            # Валидация пути
            is_valid, error_msg, target_path = self._validate_path(dir_path)
            if not is_valid:
                return self._format_error(error_msg or "Недопустимый путь")

            if target_path is None:
                return self._format_error("Внутренняя ошибка валидации пути")

            # Проверяем существование директории
            if not target_path.exists():
                return self._format_error(f"Директория не найдена: {dir_path}")

            # Проверяем, что это директория, а не файл
            if not target_path.is_dir():
                return self._format_error(
                    f"{dir_path} является файлом. Используйте инструмент для удаления файлов."
                )

            # Удаляем директорию
            if recursive:
                shutil.rmtree(str(target_path))
                return self._format_success(
                    f"Директория {dir_path} и все её содержимое успешно удалены"
                )
            else:
                target_path.rmdir()  # Удаляет только пустую директорию
                return self._format_success(
                    f"Пустая директория {dir_path} успешно удалена"
                )

        except OSError as e:
            if "Directory not empty" in str(e):
                return self._format_error(
                    f"Директория {dir_path} не пуста. Используйте recursive=true для рекурсивного удаления."
                )
            return self._format_error(
                f"Не удалось удалить директорию {dir_path}. Причина: {str(e)}"
            )
        except Exception as e:
            return self._format_error(
                f"Не удалось удалить директорию {dir_path}. Причина: {str(e)}"
            )

    async def _arun(self, dir_path: str, recursive: bool = False) -> str:
        """Асинхронная версия удаления директории"""
        return self._run(dir_path, recursive)
