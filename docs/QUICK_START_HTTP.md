# Быстрый старт с HTTP/SSE транспортами

## 🚀 За 5 минут до первого HTTP MCP сервера

### Шаг 1: Обновите зависимости

```bash
pip install -r requirements.txt
```

### Шаг 2: Настройте HTTP сервер в mcp.json

Добавьте в `mcp.json`:

```json
{
  "my-http-server": {
    "transport": "sse",
    "url": "http://localhost:3000/sse",
    "enabled": true
  }
}
```

### Шаг 3: Запустите агента

```bash
python main.py
```

Вы увидите:

```
📊 Статистика транспортов: stdio=3, sse=1, http=0
  📡 my-http-server: sse транспорт (http://localhost:3000/sse)
```

## 📝 Примеры конфигураций

### Локальный SSE сервер

```json
{
  "local-sse": {
    "transport": "sse",
    "url": "http://localhost:8080/mcp/stream",
    "enabled": true
  }
}
```

### Удаленный API с авторизацией

```json
{
  "cloud-api": {
    "transport": "streamable-http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer YOUR_API_KEY",
      "X-Custom-Header": "value"
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
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
    "transport": "stdio",
    "enabled": true
  },
  "remote-tools": {
    "transport": "sse",
    "url": "https://mcp-service.com/stream",
    "enabled": true
  }
}
```

## 🧪 Тестирование HTTP сервера

### Создайте простой тестовый сервер (Python)

```python
# test_sse_server.py
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI()

@app.get("/sse")
async def sse_endpoint():
    async def event_generator():
        tools = [
            {"name": "test_tool", "description": "Test tool", "parameters": {}}
        ]
        
        # Отправляем список инструментов
        yield {
            "event": "tools",
            "data": json.dumps({"tools": tools})
        }
        
        # Keepalive
        while True:
            await asyncio.sleep(30)
            yield {"event": "ping", "data": ""}
    
    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

### Запустите сервер

```bash
# Установите зависимости
pip install fastapi sse-starlette uvicorn

# Запустите сервер
python test_sse_server.py
```

### Проверьте подключение

```bash
curl http://localhost:3000/sse
```

### Настройте агента

В `mcp.json`:

```json
{
  "test-server": {
    "transport": "sse",
    "url": "http://localhost:3000/sse",
    "enabled": true
  }
}
```

### Запустите агента

```bash
python main.py
```

## 🔍 Отладка

### Включите DEBUG логирование

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
tail -f ai_agent.log
```

### Типичные ошибки

#### Ошибка: "отсутствует 'url' для sse транспорта"

**Решение:** Добавьте параметр `url` в конфигурацию сервера.

#### Ошибка: "невалидная схема URL"

**Решение:** URL должен начинаться с `http://` или `https://`.

#### Сервер не подключается

**Проверьте:**
1. Доступность URL: `curl http://your-server/path`
2. Firewall и сетевые настройки
3. Логи сервера

## 📚 Дополнительная информация

- [Полное руководство по HTTP транспортам](docs/HTTP_TRANSPORT_GUIDE.md)
- [Руководство по миграции](MIGRATION_V4.md)
- [Отчет об оптимизации](OPTIMIZATION_REPORT_V4.md)

## ✅ Готово!

Теперь вы можете:
- ✨ Подключаться к удаленным MCP серверам
- 🌐 Использовать облачные MCP сервисы
- 🔐 Безопасно работать с API через авторизацию
- 📊 Мониторить статус транспортов

---

**Нужна помощь?** Смотрите полную документацию или создайте issue в репозитории.

