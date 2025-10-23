# Инструкция по установке MCP серверов

Данная инструкция поможет установить все MCP серверы локально для максимальной производительности.

## Предварительные требования

```bash
# Убедитесь, что у вас установлены:
node -v  # Node.js (рекомендуется v18+)
npm -v   # NPM
python -v  # Python 3.8+
```

## Установка через NPM

### 1. Filesystem сервер
```bash
npm install -g @modelcontextprotocol/server-filesystem
```

### 2. Sequential Thinking сервер
```bash
npm install -g @modelcontextprotocol/server-sequential-thinking
```

### 3. Windows CLI сервер
```bash
npm install -g @simonb97/server-win-cli
```

## Установка через Python/UV

### 4. DuckDuckGo сервер
```bash
# Через pip
pip install duckduckgo-mcp-server

# Или через uv (рекомендуется)
uv tool install duckduckgo-mcp-server
```

### 5. Fetch сервер
```bash
# Через pip
pip install mcp-server-fetch

# Или через uv
uv tool install mcp-server-fetch
```

### 6. Blender сервер
```bash
# Через pip
pip install blender-mcp

# Или через uv
uv tool install blender-mcp
```

### 7. Excel сервер
```bash
# Через pip
pip install excel-mcp-server

# Или через uv
uv tool install excel-mcp-server
```

## Telegram MCP сервер

### 8. Telegram сервер (уже установлен)
```bash
# У вас уже установлен по пути:
# C:\Users\maks\AppData\Roaming\uv\tools\mcp-telegram\Scripts\mcp-telegram.exe
# Если нужна переустановка:
uv tool install mcp-telegram
```

## Обновленная конфигурация mcp.json

После установки обновите ваш `mcp.json`:

```json
{
  "filesystem": {
    "command": "@modelcontextprotocol/server-filesystem",
    "args": ["{filesystem_path}"],
    "transport": "stdio",
    "enabled": true
  },
  "duckduckgo": {
    "command": "duckduckgo-mcp-server",
    "args": [],
    "transport": "stdio",
    "enabled": true
  },
  "fetch": {
    "command": "mcp-server-fetch",
    "args": [],
    "transport": "stdio",
    "enabled": true
  },
  "blender": {
    "command": "blender-mcp",
    "args": [],
    "transport": "stdio",
    "enabled": false
  },
  "excel": {
    "command": "excel-mcp-server",
    "args": ["stdio"],
    "transport": "stdio",
    "enabled": false
  },
  "sequential-thinking": {
    "command": "@modelcontextprotocol/server-sequential-thinking",
    "args": [],
    "transport": "stdio",
    "enabled": true
  },
  "win-cli": {
    "command": "@simonb97/server-win-cli",
    "args": ["--config", "./win-cli-config.json"],
    "transport": "stdio",
    "enabled": true
  },
  "mcp-telegram": {
    "command": "C:\\Users\\maks\\AppData\\Roaming\\uv\\tools\\mcp-telegram\\Scripts\\mcp-telegram.exe",
    "args": ["start"],
    "env": {
      "API_ID": "28230035",
      "API_HASH": "b8c30a2a36123d66229fdcb0f1856a06"
    },
    "transport": "stdio",
    "enabled": true
  }
}
```

## Проверка установки

### Проверить NPM пакеты:
```bash
npm list -g @modelcontextprotocol/server-filesystem
npm list -g @modelcontextprotocol/server-sequential-thinking
npm list -g @simonb97/server-win-cli
```

### Проверить Python пакеты:
```bash
# Если установлено через pip
pip list | grep -E "(duckduckgo-mcp|mcp-server-fetch|blender-mcp|excel-mcp)"

# Если установлено через uv
uv tool list
```

## Альтернативные пути установки

### Если глобальная установка NPM не работает:

```bash
# Создайте локальную папку для MCP
mkdir C:\mcp-servers
cd C:\mcp-servers

# Установите пакеты локально
npm init -y
npm install @modelcontextprotocol/server-filesystem
npm install @modelcontextprotocol/server-sequential-thinking
npm install @simonb97/server-win-cli
```

Тогда в `mcp.json` используйте полные пути:
```json
{
  "filesystem": {
    "command": "node",
    "args": ["C:\\mcp-servers\\node_modules\\.bin\\server-filesystem", "{filesystem_path}"],
    "transport": "stdio",
    "enabled": true
  }
}
```

## Настройка win-cli-config.json

Создайте файл `win-cli-config.json` в той же папке, что и `mcp.json`:

```json
{
  "powershell": {
    "enabled": true,
    "timeout": 30000
  },
  "cmd": {
    "enabled": true,
    "timeout": 30000
  },
  "allowed_commands": ["*"],
  "blocked_commands": [],
  "working_directory": "C:\\Users\\maks"
}
```

## Тестирование

После установки протестируйте скорость агента. Ожидаемое время отклика должно снизиться до **5-10 секунд** для сложных запросов.

## Устранение неполадок

### Если команда не найдена:
1. Перезапустите терминал
2. Проверьте PATH: `echo $PATH` (Linux/Mac) или `echo %PATH%` (Windows)
3. Для Windows может потребоваться перезагрузка

### Если сервер не запускается:
1. Проверьте логи агента
2. Убедитесь, что порты не заняты
3. Попробуйте запустить сервер вручную для диагностики

### Если ошибки с правами доступа:
```bash
# Windows: запустите PowerShell как администратор
# Linux/Mac: используйте sudo при необходимости
```

## Рекомендуемая конфигурация для лучшей производительности

```json
{
  "filesystem": { "enabled": true },
  "win-cli": { "enabled": true },
  "mcp-telegram": { "enabled": true },
  "sequential-thinking": { "enabled": true },
  "duckduckgo": { "enabled": false },
  "fetch": { "enabled": false },
  "blender": { "enabled": false },
  "excel": { "enabled": false }
}
```

Включайте дополнительные серверы только по мере необходимости.