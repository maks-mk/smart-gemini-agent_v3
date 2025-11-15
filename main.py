#!/usr/bin/env python3
"""
Smart Gemini Agent v5.0 - Production-ready с Agent Ops, памятью, планированием и безопасностью
Точка входа для запуска агента с поддержкой всех возможностей v5.0
"""

import asyncio
import os
import json
import logging
import argparse
import signal
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console

from smart_gemini_agent import AgentConfig, FileSystemAgent, RichInteractiveChat
from smart_gemini_agent.config.logging_config import setup_logging
from smart_gemini_agent.utils.constants import (
    DEFAULT_CONFIG_FILE,
    APP_VERSION,
    APP_NAME,
    DEFAULT_LOG_LEVEL as CFG_DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_FILE as CFG_DEFAULT_LOG_FILE,
    DEFAULT_LOG_FORMAT as CFG_DEFAULT_LOG_FORMAT,
)

# Константы логирования
DEFAULT_LOG_LEVEL = getattr(logging, str(CFG_DEFAULT_LOG_LEVEL).upper(), logging.INFO)
DEFAULT_LOG_FILE = CFG_DEFAULT_LOG_FILE
DEFAULT_LOG_FORMAT = CFG_DEFAULT_LOG_FORMAT

# Глобальные переменные для graceful shutdown
shutdown_event: asyncio.Event
agent_instance: Optional[FileSystemAgent] = None


def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    print("\n⚠️  Получен сигнал прерывания (Ctrl+C). Останавливаем агента...")
    shutdown_event.set()
    
    # Просто устанавливаем флаг - cleanup будет вызван в main()
    # Выходим через KeyboardInterrupt для корректной обработки в asyncio
    raise KeyboardInterrupt


def load_logging_config(config_file: str) -> tuple[int, str, str]:
    """Загрузка конфигурации логирования из файла"""
    log_level = DEFAULT_LOG_LEVEL
    log_file = DEFAULT_LOG_FILE
    log_format = DEFAULT_LOG_FORMAT
    
    try:
        config_path = Path(config_file)
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            
            logging_cfg = cfg.get("logging", {})
            level_str = str(logging_cfg.get("level", "INFO")).upper()
            log_level = getattr(logging, level_str, logging.INFO)
            log_file = logging_cfg.get("file", log_file)
            log_format = logging_cfg.get("format", log_format)
    except Exception as e:
        print(f"⚠️  Ошибка загрузки конфигурации логирования: {e}")
        print("Используются настройки по умолчанию")
    
    return log_level, log_file, log_format


def _apply_environment_overrides(config: AgentConfig) -> AgentConfig:
    """Применение переопределений из переменных окружения"""
    # Переопределяем путь файловой системы
    filesystem_path_env = os.getenv("FILESYSTEM_PATH")
    if filesystem_path_env:
        config.filesystem_path = filesystem_path_env
        logging.info(f"Путь filesystem переопределен из ENV: {filesystem_path_env}")

    # Переопределяем модель и провайдер из ENV (приоритет ENV > config)
    gemini_model_env = os.getenv("GEMINI_MODEL")
    openrouter_model_env = os.getenv("OPENROUTER_MODEL")
    openai_model_env = os.getenv("OPENAI_MODEL")
    openai_base_url_env = os.getenv("OPENAI_BASE_URL")

    if gemini_model_env:
        config.model_name = gemini_model_env
        config.model_provider = "gemini"
        logging.info(f"Используется модель Gemini из ENV: {gemini_model_env}")
    elif openrouter_model_env or openai_model_env:
        # OpenRouter и OpenAI - это OpenAI-совместимые провайдеры
        model_name = openrouter_model_env or openai_model_env
        config.model_name = model_name
        config.model_provider = "openai"
        logging.info(f"Используется OpenAI-совместимая модель из ENV: {model_name}")
        if openai_base_url_env:
            os.environ["OPENAI_BASE_URL"] = openai_base_url_env
            logging.info(f"Установлен OpenAI Base URL из ENV: {openai_base_url_env}")

    # Переопределяем температуру
    temperature_env = os.getenv("TEMPERATURE")
    if temperature_env:
        try:
            config.temperature = float(temperature_env)
            logging.info(f"Температура переопределена из ENV: {temperature_env}")
        except ValueError:
            logging.warning(f"Невалидное значение TEMPERATURE в ENV: {temperature_env}")
    
    return config


async def main(config_file: str = DEFAULT_CONFIG_FILE):
    """Главная функция с Rich интерфейсом и оптимизированной загрузкой конфигурации"""
    load_dotenv()

    # Загрузка конфигурации логирования
    log_level, log_file, log_format = load_logging_config(config_file)
    
    # Настройка логирования согласно конфиг
    logger = setup_logging(level=log_level, log_file=log_file, format_string=log_format)

    console = Console()
    
    try:
        # Создание конфигурации из файла или переменных окружения
        config = AgentConfig.from_file(config_file)

        # Переопределяем из переменных окружения если они заданы
        config = _apply_environment_overrides(config)
        
        # Валидация конфигурации
        config.validate()

        # Создание и инициализация агента
        agent = FileSystemAgent(config)
        
        # Сохраняем ссылку для обработчика сигналов
        global agent_instance
        agent_instance = agent

        # Показываем прогресс инициализации
        with console.status(f"[bold green]Initializing {APP_NAME} v{APP_VERSION}...", spinner="dots"):
            if not await agent.initialize():
                console.print(
                    "❌ [bold red]Не удалось инициализировать агента. Проверьте логи.[/bold red]"
                )
                return

        console.print(
            f"✅ [bold green]{APP_NAME} v{APP_VERSION} successfully initialized![/bold green]"
        )
        console.print(
            f"[cyan]Модель:[/cyan] {config.model_name} ({config.model_provider})"
        )
        console.print(
            f"[cyan]Рабочая директория:[/cyan] {config.filesystem_path}"
        )

        # Запуск богатого чата
        chat = RichInteractiveChat(agent)
        try:
            await chat.run()
        except KeyboardInterrupt:
            console.print("\n⚠️  [yellow]Прервано пользователем[/yellow]")
            logger.info("🏁 Завершение работы (прервано пользователем)")
        finally:
            # Корректное закрытие агента
            await agent.cleanup()

    except KeyboardInterrupt:
        Console().print("\n⚠️  [yellow]Прервано пользователем[/yellow]")
        logger.info("🏁 Завершение работы (прервано)")
    except Exception as e:
        Console().print(f"❌ [bold red]Критическая ошибка: {e}[/bold red]")
        logger.error(f"Критическая ошибка: {e}", exc_info=True)

    logger.info("🏁 Завершение работы")


if __name__ == "__main__":
    # Инициализация события завершения
    shutdown_event = asyncio.Event()
    # Настройка обработчиков сигналов
    if sys.platform != "win32":
        # Unix-подобные системы
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    else:
        # Windows - используем другой подход
        signal.signal(signal.SIGINT, signal_handler)
        # SIGTERM не поддерживается в Windows, используем SIGBREAK или CTRL_C_EVENT
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, signal_handler)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION} - Production-ready AI агент с Agent Ops, памятью, планированием и безопасностью",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                    # Запуск с конфигурацией по умолчанию
  python main.py --config custom.json  # Запуск с кастомной конфигурацией
  
Переменные окружения:
  GOOGLE_API_KEY      - API ключ для Google Gemini
  OPENAI_API_KEY      - API ключ для OpenAI
  FILESYSTEM_PATH     - Путь к рабочей директории
  TEMPERATURE         - Температура модели (0.0-1.0)
        """
    )
    parser.add_argument(
        "--config", 
        type=str, 
        default=DEFAULT_CONFIG_FILE, 
        help="Путь к файлу конфигурации (по умолчанию: config.json)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.config))
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
        sys.exit(0)
