# 🚨 Решение проблемы зависания агента

## 🔍 Обнаруженные причины

### 1. **Экстремально длинный таймаут win-cli**
```json
"commandTimeout": 300  // 5 минут!!!
```
❌ **Проблема:** Команды могут выполняться до 5 минут без возможности прервать

### 2. **Отсутствие таймаутов для MCP операций**
- Нет общего таймаута для `process_message`
- MCP клиент может зависнуть на неотвечающем сервере
- Нет обработки зависших инструментов

### 3. **Блокирующий await без таймаута**
```python
async for chunk in self.agent.astream(message_input, config):
    # Если инструмент зависает - всё зависает!
```

### 4. **Нет graceful shutdown**
- Ctrl+C не всегда корректно прерывает операции
- MCP подпроцессы могут остаться висеть

---

## ✅ Решения

### Решение 1: Уменьшить таймауты (СРОЧНО)

Отредактируйте `win-cli-config.json`:

```json
{
  "security": {
    "commandTimeout": 30,  // Было: 300 → Стало: 30 секунд
    ...
  }
}
```

### Решение 2: Добавить глобальный таймаут

Создайте файл `smart_gemini_agent/utils/timeout.py`:

```python
"""Утилиты для обработки таймаутов"""
import asyncio
import logging
from typing import AsyncGenerator, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

async def async_timeout_wrapper(
    coro,
    timeout: float = 60.0,
    error_message: str = "Операция превысила таймаут"
) -> T:
    """Обертка с таймаутом для асинхронных операций"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"{error_message} ({timeout}с)")
        raise TimeoutError(f"{error_message} ({timeout}с)")


async def async_gen_timeout_wrapper(
    gen: AsyncGenerator[T, None],
    timeout: float = 60.0,
    per_item_timeout: float = 30.0
) -> AsyncGenerator[T, None]:
    """Обертка с таймаутом для асинхронных генераторов"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        async for item in gen:
            # Проверяем общий таймаут
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.warning(f"Операция превысила лимит {timeout}с")
                break
            
            # Выдаем элемент с таймаутом
            yield item
            
    except asyncio.CancelledError:
        logger.info("Операция прервана пользователем")
        raise
```

### Решение 3: Обновить agent.py

Добавьте таймауты в `process_message`:

```python
# В начале файла
import asyncio

# В методе process_message добавьте таймауты
@retry_on_failure_async_gen()
async def process_message(
    self, user_input: str, thread_id: str = "default", timeout: float = 120.0
) -> AsyncGenerator[Dict, None]:
    """Умная обработка сообщения с таймаутом"""
    
    if not self.is_ready:
        yield {"error": "Агент не готов"}
        return

    start_time = time.time()
    
    try:
        # ... существующий код ...
        
        # Добавьте таймаут для стриминга
        async for chunk in asyncio.wait_for(
            self._stream_with_timeout(message_input, config),
            timeout=timeout
        ):
            # Проверка времени выполнения
            elapsed = time.time() - start_time
            if elapsed > timeout:
                yield {"error": f"Timeout: операция превысила {timeout}с"}
                return
            
            yield chunk
            
    except asyncio.TimeoutError:
        yield {
            "error": f"⏱️ Timeout: запрос занял больше {timeout}с\n"
                     f"Fix: упростите запрос | отключите медленные инструменты"
        }
    # ... остальной код ...

async def _stream_with_timeout(self, message_input, config):
    """Вспомогательный метод для стриминга с контролем"""
    async for chunk in self.agent.astream(message_input, config):
        yield chunk
```

### Решение 4: Улучшить обработку Ctrl+C

Добавьте в `main.py`:

```python
import signal

# Глобальный флаг для graceful shutdown
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    print("\n⚠️ Получен сигнал прерывания. Останавливаем агента...")
    shutdown_event.set()

# В функции main() перед запуском:
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

---

## 🛠️ Быстрое исправление (ПРИМЕНИТЬ СЕЙЧАС)

### Шаг 1: Обновите win-cli-config.json

```json
{
  "security": {
    "commandTimeout": 30,
    "maxCommandLength": 2000,
    ...
  }
}
```

### Шаг 2: Добавьте таймауты в config.json

```json
{
  "agent": {
    "model_name": "gemini-2.0-flash-exp",
    "temperature": 0.2,
    "request_timeout": 120,
    "tool_timeout": 30
  }
}
```

### Шаг 3: Отключите проблемные серверы

В `mcp.json` отключите потенциально зависающие серверы:

```json
{
  "playwright": {
    "enabled": false  // Часто зависает
  },
  "chrome-mcp": {
    "enabled": false  // Может зависнуть на неотвечающем Chrome
  },
  "mcp-telegram": {
    "enabled": false  // Telegram API может тормозить
  }
}
```

---

## 📊 Диагностика зависания

### Включите подробное логирование

В `config.json`:

```json
{
  "logging": {
    "level": "DEBUG",
    "file": "ai_agent.log"
  }
}
```

### Проверьте логи

```bash
# Посмотрите последние строки лога
tail -f ai_agent.log

# Windows PowerShell
Get-Content ai_agent.log -Wait -Tail 20
```

### Типичные признаки зависания в логах:

```
# Зависание на инструменте
INFO - Вызов инструмента: win_cli_execute
# ... тишина 5 минут ...

# Зависание на MCP сервере
INFO - Инициализация MCP клиента...
# ... тишина ...

# Зависание на модели
INFO - Отправка запроса к Gemini...
# ... тишина ...
```

---

## 🔧 Дополнительные меры

### 1. Добавьте мониторинг живости

Создайте `smart_gemini_agent/utils/watchdog.py`:

```python
"""Watchdog для отслеживания зависших операций"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class OperationWatchdog:
    """Следит за длительностью операций"""
    
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.active_operations = {}
    
    async def monitor(self, operation_id: str):
        """Мониторинг операции с автопрерыванием"""
        self.active_operations[operation_id] = datetime.now()
        
        try:
            await asyncio.sleep(self.timeout)
            if operation_id in self.active_operations:
                logger.warning(
                    f"⚠️ Операция {operation_id} выполняется более {self.timeout}с"
                )
        finally:
            self.active_operations.pop(operation_id, None)
    
    def complete(self, operation_id: str):
        """Отметить операцию как завершенную"""
        self.active_operations.pop(operation_id, None)
```

### 2. Ограничьте рекурсию

В `agent.py` уже есть `recursion_limit: 50`, но можно уменьшить:

```python
config: RunnableConfig = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": 20  # Было: 50 → Стало: 20
}
```

### 3. Добавьте heartbeat

```python
# В process_message добавьте периодический heartbeat
last_heartbeat = time.time()

async for chunk in self.agent.astream(message_input, config):
    current_time = time.time()
    if current_time - last_heartbeat > 10:
        logger.debug(f"💓 Heartbeat: операция активна ({current_time - start_time:.1f}с)")
        last_heartbeat = current_time
    
    yield chunk
```

---

## ⚡ Экстренное восстановление

### Если агент завис прямо сейчас:

#### Windows:
```powershell
# Найти и убить процесс
tasklist | findstr python
taskkill /F /PID <PID>

# Или убить все Python процессы (осторожно!)
taskkill /F /IM python.exe

# Убить зависшие Node.js процессы (MCP серверы)
taskkill /F /IM node.exe
```

#### Linux/Mac:
```bash
# Найти процесс
ps aux | grep python

# Убить процесс
kill -9 <PID>

# Убить все связанные процессы
pkill -9 -f "smart-gemini-agent"

# Убить MCP серверы
pkill -9 -f "mcp-server"
pkill -9 node
```

---

## 📋 Чек-лист профилактики

- [ ] Уменьшить `commandTimeout` с 300 до 30 секунд
- [ ] Добавить `request_timeout` в config.json
- [ ] Отключить проблемные MCP серверы
- [ ] Включить DEBUG логирование
- [ ] Добавить таймауты в process_message
- [ ] Настроить graceful shutdown
- [ ] Уменьшить recursion_limit до 20
- [ ] Периодически проверять логи

---

## 🎯 Рекомендуемая конфигурация

### config.json
```json
{
  "logging": {
    "level": "INFO",
    "file": "ai_agent.log"
  },
  "agent": {
    "model_name": "gemini-2.0-flash-exp",
    "temperature": 0.2,
    "use_memory": true,
    "max_context_files": 20,
    "request_timeout": 120,
    "tool_timeout": 30,
    "recursion_limit": 20
  }
}
```

### win-cli-config.json
```json
{
  "security": {
    "commandTimeout": 30,
    "maxCommandLength": 2000,
    ...
  }
}
```

### mcp.json
```json
{
  "filesystem": { "enabled": true },
  "duckduckgo": { "enabled": true },
  "fetch": { "enabled": true },
  "sequential-thinking": { "enabled": true },
  "win-cli": { "enabled": true },
  
  "playwright": { "enabled": false },
  "chrome-mcp": { "enabled": false },
  "mcp-telegram": { "enabled": false }
}
```

---

## 📞 Если проблема не решена

1. **Соберите диагностику:**
   - Скопируйте последние 100 строк из `ai_agent.log`
   - Опишите какой запрос вызвал зависание
   - Укажите, какие MCP серверы включены

2. **Попробуйте минимальную конфигурацию:**
   - Отключите все MCP серверы кроме `filesystem`
   - Если работает - включайте по одному

3. **Проверьте системные ресурсы:**
   ```bash
   # Процессор и память
   top  # Linux/Mac
   taskmgr  # Windows
   ```

---

**Дата создания:** 2025-11-03  
**Версия:** v4.0-troubleshooting

