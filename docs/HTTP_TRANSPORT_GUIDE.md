# Руководство по использованию HTTP/SSE транспортов для MCP серверов

## Обзор

Smart Gemini Agent v4.0 поддерживает три типа транспортов для подключения MCP серверов:

1. **stdio** - стандартный ввод/вывод (локальные процессы)
2. **sse** - Server-Sent Events (HTTP streaming)
3. **streamable-http** - Streamable HTTP (двунаправленный HTTP streaming)

## Конфигурация транспортов

### 1. STDIO транспорт (по умолчанию)

Используется для локальных MCP серверов, запускаемых как процессы:

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"],
    "transport": "stdio",
    "enabled": true
  }
}
```

**Параметры:**
- `command` - команда для запуска процесса
- `args` - аргументы команды
- `transport` - тип транспорта ("stdio")
- `enabled` - включен ли сервер
- `env` (опционально) - переменные окружения

### 2. SSE транспорт (Server-Sent Events)

Используется для подключения к удаленным MCP серверам через HTTP SSE:

```json
{
  "remote-mcp-server": {
    "transport": "sse",
    "url": "http://localhost:3000/sse",
    "enabled": true
  }
}
```

**Параметры:**
- `transport` - тип транспорта ("sse")
- `url` - URL эндпоинта SSE
- `enabled` - включен ли сервер
- `headers` (опционально) - HTTP заголовки

**Пример с заголовками:**

```json
{
  "secure-remote-mcp": {
    "transport": "sse",
    "url": "https://api.example.com/mcp/stream",
    "headers": {
      "Authorization": "Bearer YOUR_API_KEY",
      "X-Custom-Header": "value"
    },
    "enabled": true
  }
}
```

### 3. Streamable HTTP транспорт

Используется для двунаправленного HTTP streaming:

```json
{
  "http-mcp-server": {
    "transport": "streamable-http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer YOUR_API_KEY",
      "Content-Type": "application/json"
    },
    "enabled": true
  }
}
```

**Параметры:**
- `transport` - тип транспорта ("streamable-http")
- `url` - URL эндпоинта
- `enabled` - включен ли сервер
- `headers` (опционально) - HTTP заголовки

## Примеры использования

### Локальный SSE сервер

```json
{
  "local-sse-mcp": {
    "transport": "sse",
    "url": "http://localhost:8080/mcp/stream",
    "enabled": true,
    "description": "Локальный HTTP MCP сервер через SSE"
  }
}
```

### Удаленный API с аутентификацией

```json
{
  "cloud-mcp-service": {
    "transport": "streamable-http",
    "url": "https://mcp.cloud-service.com/api/v1/stream",
    "headers": {
      "Authorization": "Bearer sk-1234567890abcdef",
      "X-API-Version": "1.0"
    },
    "enabled": true
  }
}
```

### Смешанная конфигурация

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/projects"],
    "transport": "stdio",
    "enabled": true
  },
  "duckduckgo": {
    "command": "uvx",
    "args": ["duckduckgo-mcp-server"],
    "transport": "stdio",
    "enabled": true
  },
  "cloud-tools": {
    "transport": "sse",
    "url": "https://api.example.com/mcp/tools",
    "headers": {
      "Authorization": "Bearer YOUR_TOKEN"
    },
    "enabled": true
  }
}
```

## Валидация конфигурации

Агент автоматически валидирует конфигурацию при запуске:

### Для stdio транспорта:
- ✅ Обязателен параметр `command`
- ✅ Проверяется наличие исполняемого файла

### Для HTTP транспортов (sse/streamable-http):
- ✅ Обязателен параметр `url`
- ✅ URL должен иметь схему http или https
- ✅ URL должен содержать корректный хост

При обнаружении ошибок в конфигурации сервер будет пропущен с записью в лог:

```
⚠️ Сервер example-server пропущен из-за невалидной конфигурации
❌ Сервер example-server: отсутствует 'url' для sse транспорта
```

## Статистика транспортов

При запуске агента отображается статистика используемых транспортов:

```
📊 Статистика транспортов: stdio=3, sse=1, http=1
  💻 filesystem: stdio транспорт (npx)
  💻 duckduckgo: stdio транспорт (uvx)
  📡 cloud-tools: sse транспорт (https://api.example.com/mcp/tools)
```

## Переменные окружения

Вы можете использовать переменные окружения для хранения секретов:

**.env файл:**
```bash
MCP_API_KEY=your-secret-api-key
MCP_BASE_URL=https://api.example.com
```

**mcp.json:**
```json
{
  "secure-mcp": {
    "transport": "sse",
    "url": "${MCP_BASE_URL}/mcp/stream",
    "headers": {
      "Authorization": "Bearer ${MCP_API_KEY}"
    },
    "enabled": true
  }
}
```

⚠️ **Примечание:** Подстановка переменных окружения в mcp.json пока не реализована автоматически. Используйте это как паттерн для будущей реализации.

## Отладка

Для включения детального логирования:

**config.json:**
```json
{
  "logging": {
    "level": "DEBUG",
    "file": "ai_agent.log"
  }
}
```

В логах будут отображаться:
- Информация о загруженных серверах
- Детали транспортов
- Ошибки подключения
- HTTP запросы/ответы

## Требования

Для работы HTTP транспортов необходимы следующие пакеты:

```bash
pip install httpx>=0.24.0
pip install aiohttp>=3.8.0
pip install sse-starlette>=1.6.0
```

Или установите все зависимости:

```bash
pip install -r requirements.txt
```

## Устранение неполадок

### Ошибка: "отсутствует 'url' для sse транспорта"

**Решение:** Убедитесь, что параметр `url` указан в конфигурации сервера.

### Ошибка: "невалидная схема URL"

**Решение:** URL должен начинаться с `http://` или `https://`.

### Сервер не подключается

**Проверьте:**
1. Доступность URL (curl/wget)
2. Корректность заголовков аутентификации
3. Firewall и сетевые настройки
4. Логи агента для деталей ошибки

### Таймаут подключения

**Настройка таймаутов в config.json:**
```json
{
  "agent": {
    "request_timeout": 300,
    "tool_timeout": 300
  }
}
```

## Примеры MCP серверов

### Простой SSE сервер на Python

```python
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
import asyncio

app = FastAPI()

@app.get("/mcp/stream")
async def mcp_stream():
    async def event_generator():
        while True:
            # Отправка MCP событий
            yield {
                "event": "tool",
                "data": '{"name": "example", "result": "data"}'
            }
            await asyncio.sleep(1)
    
    return EventSourceResponse(event_generator())

# Запуск: uvicorn server:app --host 0.0.0.0 --port 8080
```

### Node.js SSE сервер

```javascript
const express = require('express');
const app = express();

app.get('/mcp/stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
  });

  const interval = setInterval(() => {
    res.write(`data: ${JSON.stringify({tool: 'example'})}\n\n`);
  }, 1000);

  req.on('close', () => clearInterval(interval));
});

app.listen(8080);
```

## Безопасность

### Рекомендации:

1. **Используйте HTTPS** для удаленных подключений
2. **Храните API ключи** в переменных окружения
3. **Ограничьте доступ** к MCP серверам через firewall
4. **Валидируйте данные** от удаленных серверов
5. **Логируйте** все подключения для аудита

## Дополнительные ресурсы

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Server-Sent Events MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [HTTP/2 Streaming](https://http2.github.io/)

## Обратная связь

Если вы столкнулись с проблемами или у вас есть предложения по улучшению, создайте issue в репозитории проекта.

