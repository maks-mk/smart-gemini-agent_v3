"""Утилиты для обработки таймаутов и предотвращения зависаний"""
import asyncio
import logging
from typing import AsyncGenerator, TypeVar, Coroutine, Any
from datetime import datetime

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def async_timeout_wrapper(
    coro: Coroutine[Any, Any, T],
    timeout: float = 60.0,
    error_message: str = "Операция превысила таймаут"
) -> T:
    """
    Обертка с таймаутом для асинхронных операций
    
    Args:
        coro: Корутина для выполнения
        timeout: Таймаут в секундах
        error_message: Сообщение об ошибке
        
    Returns:
        Результат корутины
        
    Raises:
        TimeoutError: Если операция превысила таймаут
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"{error_message} ({timeout}с)")
        raise TimeoutError(f"{error_message} ({timeout}с)")


async def async_gen_timeout_wrapper(
    gen: AsyncGenerator[T, None],
    timeout: float = 300.0,
    per_item_timeout: float = 300.0,
    heartbeat_interval: float = 10.0
) -> AsyncGenerator[T, None]:
    """
    Обертка с таймаутом для асинхронных генераторов
    
    Args:
        gen: Асинхронный генератор
        timeout: Общий таймаут операции в секундах
        per_item_timeout: Таймаут на получение каждого элемента
        heartbeat_interval: Интервал для heartbeat логирования
        
    Yields:
        Элементы из генератора
        
    Raises:
        TimeoutError: Если операция превысила таймаут
        asyncio.CancelledError: Если операция прервана
    """
    start_time = asyncio.get_event_loop().time()
    last_heartbeat = start_time
    item_count = 0
    
    try:
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            # Проверяем общий таймаут
            if elapsed > timeout:
                logger.warning(f"⏱️ Общий таймаут: операция превысила {timeout}с")
                raise TimeoutError(f"Операция превысила лимит {timeout}с")
            
            # Heartbeat
            if current_time - last_heartbeat > heartbeat_interval:
                logger.debug(
                    f"💓 Heartbeat: {item_count} элементов, {elapsed:.1f}с"
                )
                last_heartbeat = current_time
            
            # Получаем следующий элемент с таймаутом
            try:
                remaining_time = min(per_item_timeout, timeout - elapsed)
                item = await asyncio.wait_for(
                    gen.__anext__(),
                    timeout=remaining_time
                )
                item_count += 1
                yield item
                
            except StopAsyncIteration:
                logger.debug(f"✅ Генератор завершен: {item_count} элементов за {elapsed:.1f}с")
                break
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Таймаут ожидания элемента: {per_item_timeout}с")
                raise TimeoutError(
                    f"Таймаут ожидания следующего элемента ({per_item_timeout}с)"
                )
                
    except asyncio.CancelledError:
        logger.info("🛑 Операция прервана пользователем")
        raise
    except Exception as e:
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.error(f"❌ Ошибка после {elapsed:.1f}с: {e}")
        raise


class OperationWatchdog:
    """
    Watchdog для отслеживания и автоматического прерывания зависших операций
    """
    
    def __init__(self, default_timeout: float = 60.0):
        """
        Args:
            default_timeout: Таймаут по умолчанию в секундах
        """
        self.default_timeout = default_timeout
        self.active_operations: dict[str, tuple[datetime, asyncio.Task]] = {}
        self._cleanup_task: asyncio.Task | None = None
    
    async def start(self):
        """Запуск фонового мониторинга"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_check())
            logger.info("🐕 Watchdog запущен")
    
    async def stop(self):
        """Остановка watchdog"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("🐕 Watchdog остановлен")
    
    def register_operation(
        self,
        operation_id: str,
        task: asyncio.Task,
        timeout: float | None = None
    ):
        """
        Регистрация операции для мониторинга
        
        Args:
            operation_id: Уникальный идентификатор операции
            task: Task для мониторинга
            timeout: Таймаут для этой операции (или default)
        """
        actual_timeout = timeout or self.default_timeout
        deadline = datetime.now()
        self.active_operations[operation_id] = (deadline, task)
        logger.debug(f"📝 Зарегистрирована операция: {operation_id} (timeout: {actual_timeout}с)")
    
    def complete_operation(self, operation_id: str):
        """
        Отметить операцию как завершенную
        
        Args:
            operation_id: Идентификатор операции
        """
        if operation_id in self.active_operations:
            self.active_operations.pop(operation_id)
            logger.debug(f"✅ Операция завершена: {operation_id}")
    
    async def _periodic_check(self):
        """Периодическая проверка зависших операций"""
        while True:
            try:
                await asyncio.sleep(5)  # Проверка каждые 5 секунд
                
                now = datetime.now()
                for op_id, (deadline, task) in list(self.active_operations.items()):
                    age = (now - deadline).total_seconds()
                    
                    # Предупреждение если операция выполняется долго
                    if age > self.default_timeout / 2:
                        logger.warning(
                            f"⚠️ Операция {op_id} выполняется уже {age:.0f}с"
                        )
                    
                    # Принудительное прерывание при превышении таймаута
                    if age > self.default_timeout and not task.done():
                        logger.error(
                            f"🚨 TIMEOUT: Принудительное прерывание {op_id} после {age:.0f}с"
                        )
                        task.cancel()
                        self.active_operations.pop(op_id, None)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка watchdog: {e}")
    
    def get_active_operations(self) -> dict[str, float]:
        """
        Получить список активных операций и их возраст
        
        Returns:
            Словарь {operation_id: age_in_seconds}
        """
        now = datetime.now()
        return {
            op_id: (now - deadline).total_seconds()
            for op_id, (deadline, _) in self.active_operations.items()
        }


# Глобальный экземпляр watchdog
_global_watchdog: OperationWatchdog | None = None


def get_watchdog() -> OperationWatchdog:
    """Получить глобальный экземпляр watchdog"""
    global _global_watchdog
    if _global_watchdog is None:
        _global_watchdog = OperationWatchdog(default_timeout=300.0)
    return _global_watchdog

