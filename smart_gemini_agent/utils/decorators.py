"""
Декораторы для Smart Gemini Agent с оптимизированной обработкой ошибок
"""

import asyncio
import logging
import re
from functools import wraps
from typing import Callable, Any, AsyncGenerator, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

# Предкомпилированные регулярные выражения для производительности
_RETRY_DELAY_PATTERN = re.compile(r"retry_delay\s*{\s*seconds:\s*(\d+)")

# Type variables для строгой типизации
P = ParamSpec("P")
T = TypeVar("T")


def _extract_retry_delay(error_text: str, default_delay: float) -> float:
    """Извлекает время задержки из текста ошибки (общая функция)"""
    match = _RETRY_DELAY_PATTERN.search(error_text)
    return float(match.group(1)) if match else default_delay


def _is_rate_limit_error(error_text: str) -> bool:
    """Проверяет, является ли ошибка превышением лимита запросов"""
    return "429" in error_text or "ResourceExhausted" in error_text


def retry_on_failure(max_retries: int = 2, delay: float = 1.0):
    """
    Декоратор для повторения асинхронных операций при неудаче.
    
    Args:
        max_retries: Максимальное количество попыток
        delay: Задержка между попытками в секундах
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_text = str(e)

                    if _is_rate_limit_error(error_text):
                        wait_time = _extract_retry_delay(error_text, delay)
                        logger.warning(
                            f"Превышены лимиты API (429). Попытка {attempt + 1}/{max_retries} неудачна, повтор через {wait_time}с"
                        )
                        await asyncio.sleep(wait_time)
                    elif attempt < max_retries - 1:
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_retries} неудачна, повтор через {delay}с"
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise e
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def retry_on_failure_async_gen(max_retries: int = 2, delay: float = 1.0):
    """
    Декоратор для повторения операций асинхронного генератора при неудаче.
    
    Args:
        max_retries: Максимальное количество попыток
        delay: Задержка между попытками в секундах
    """

    def decorator(func: Callable[P, AsyncGenerator[T, None]]) -> Callable[P, AsyncGenerator[T, None]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[T, None]:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    async for item in func(*args, **kwargs):
                        yield item
                    return
                except Exception as e:
                    last_exception = e
                    error_text = str(e)

                    if _is_rate_limit_error(error_text):
                        wait_time = _extract_retry_delay(error_text, delay)
                        logger.warning(
                            f"Превышены лимиты API (429). Попытка {attempt + 1}/{max_retries} неудачна, повтор через {wait_time}с"
                        )
                        await asyncio.sleep(wait_time)
                    elif attempt < max_retries - 1:
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_retries} неудачна, повтор через {delay}с"
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise e
            if last_exception:
                raise last_exception

        return wrapper

    return decorator
