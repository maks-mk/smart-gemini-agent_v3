#!/usr/bin/env python3
"""
Smart Gemini Agent v3.0 - Модульная версия с оптимизированной производительностью
Точка входа для запуска агента
"""

import asyncio
import os
import json
import logging
import argparse
from dotenv import load_dotenv
from rich.console import Console

from smart_gemini_agent import AgentConfig, FileSystemAgent, RichInteractiveChat
from smart_gemini_agent.config.logging_config import setup_logging

# Константы по умолчанию
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FILE = "ai_agent.log"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DEFAULT_CONFIG_FILE = "config.json"


async def main(config_file: str = DEFAULT_CONFIG_FILE):
    """Главная функция с Rich интерфейсом и оптимизированной загрузкой конфигурации"""
    load_dotenv()

    # Загрузка конфигурации из файла для настройки логирования
    log_level = DEFAULT_LOG_LEVEL
    log_file = DEFAULT_LOG_FILE
    log_format = DEFAULT_LOG_FORMAT
    try:
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            logging_cfg = cfg.get("logging", {})
            level_str = str(logging_cfg.get("level", "INFO")).upper()
            log_level = getattr(logging, level_str, logging.INFO)
            log_file = logging_cfg.get("file", log_file)
            log_format = logging_cfg.get("format", log_format)
    except Exception:
        # В случае ошибки применяем значения по умолчанию
        pass

    # Настройка логирования согласно конфиг
    logger = setup_logging(level=log_level, log_file=log_file, format_string=log_format)

    try:
        # Создание конфигурации из файла или переменных окружения
        config = AgentConfig.from_file(config_file)

        # Переопределяем из переменных окружения если они заданы
        filesystem_path_env = os.getenv("FILESYSTEM_PATH")
        if filesystem_path_env:
            config.filesystem_path = filesystem_path_env

        gemini_model_env = os.getenv("GEMINI_MODEL")
        if gemini_model_env:
            config.model_name = gemini_model_env
            config.model_provider = "gemini"

        openrouter_model_env = os.getenv("OPENROUTER_MODEL")
        if openrouter_model_env:
            config.model_name = openrouter_model_env
            config.model_provider = "openrouter"

        temperature_env = os.getenv("TEMPERATURE")
        if temperature_env:
            config.temperature = float(temperature_env)

        # Создание и инициализация агента
        agent = FileSystemAgent(config)

        # Создаем богатый интерфейс для показа прогресса инициализации
        console = Console()

        with console.status("[bold green]Initializing Gemini Agent...", spinner="dots"):
            if not await agent.initialize():
                console.print(
                    "❌ [bold red]Не удалось инициализировать агента[/bold red]"
                )
                return

        console.print(
            "✅ [bold green]Gemini Agent successfully initialized![/bold green]"
        )

        # Запуск богатого чата
        chat = RichInteractiveChat(agent)
        await chat.run()

    except Exception as e:
        Console().print(f"❌ [bold red]Критическая ошибка: {e}[/bold red]")

    logger.info("🏁 Завершение работы")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Smart Gemini Agent v3.0 - Интеллектуальный AI ассистент с оптимизированной производительностью"
    )
    parser.add_argument(
        "--config", 
        type=str, 
        default=DEFAULT_CONFIG_FILE, 
        help="Path to config file (default: config.json)"
    )
    args = parser.parse_args()

    asyncio.run(main(args.config))
