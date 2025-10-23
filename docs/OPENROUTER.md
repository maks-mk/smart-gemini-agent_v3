# Поддержка моделей OpenRouter

Теперь Smart Gemini Agent поддерживает не только модели Google Gemini, но и любые модели из экосистемы OpenRouter.

## Как использовать модели OpenRouter

### 1. Получение API ключа OpenRouter

1. Перейдите на сайт [https://openrouter.ai](https://openrouter.ai)
2. Зарегистрируйтесь или войдите в свой аккаунт
3. Перейдите в раздел API Keys
4. Создайте новый API ключ
5. Скопируйте ключ

### 2. Настройка переменной окружения

Создайте файл `.env` в корневой директории проекта (или переименуйте `.env.example` в `.env`) и добавьте ваш API ключ:

```
# Google Gemini API Key (опционально)
GOOGLE_API_KEY=your_gemini_api_key_here

# OpenRouter API Key
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

Или установите переменную окружения в вашей системе:

**В Windows (PowerShell):**
```powershell
$env:OPENROUTER_API_KEY="ваш_ключ_здесь"
```

**В Linux/macOS:**
```bash
export OPENROUTER_API_KEY="ваш_ключ_здесь"
```

### 3. Настройка конфигурации

Измените файл `config.json`, чтобы использовать модель OpenRouter:

```json
{
  "agent": {
    "model_name": "openai/gpt-4o-mini",
    "model_provider": "openrouter",
    "temperature": 0.1,
    "use_memory": true,
    "max_context_files": 20
  },
  "logging": {
    "level": "INFO",
    "file": "ai_agent.log",
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "debug_intent_analysis": false
  },
  "files": {
    "prompt_file": "prompt_optimized.md",
    "mcp_config_file": "mcp.json",
    "intents_file": "intents.json"
  },
  "interface": {
    "show_timestamps": true,
    "theme": "dark",
    "max_response_length": 1000,
    "improve_file_formatting": true,
    "syntax_highlighting": true
  }
}
```

Или создайте отдельный файл конфигурации и используйте его при запуске:

```bash
python main.py --config your-openrouter-config.json
```

### 4. Популярные модели OpenRouter

Вот несколько популярных моделей, которые вы можете использовать:

- `openai/gpt-4o-mini` - Экономичная модель от OpenAI
- `openai/gpt-4o` - Мощная модель от OpenAI
- `anthropic/claude-3.5-sonnet` - Модель от Anthropic
- `meta-llama/llama-3.1-70b-instruct` - Модель от Meta
- `mistralai/mistral-large` - Модель от Mistral AI
- `google/gemini-pro` - Альтернативный доступ к Gemini через OpenRouter

### 5. Запуск агента

После настройки конфигурации просто запустите агент как обычно:

```bash
python main.py
```

Или с пользовательским файлом конфигурации:

```bash
python main.py --config test-openrouter-config.json
```

## Переключение между провайдерами

Вы можете легко переключаться между Google Gemini и OpenRouter, изменяя параметры в `config.json`:

**Для Google Gemini:**
```json
{
  "agent": {
    "model_name": "gemini-2.5-flash",
    "model_provider": "gemini"
  }
}
```

**Для OpenRouter:**
```json
{
  "agent": {
    "model_name": "openai/gpt-4o-mini",
    "model_provider": "openrouter"
  }
}
```

Также вы можете использовать переменные окружения для переключения между моделями:

```
# Для использования модели Gemini
GEMINI_MODEL=gemini-2.5-flash

# Для использования модели OpenRouter
OPENROUTER_MODEL=openai/gpt-4o-mini
```

## Преимущества использования OpenRouter

1. **Доступ к множеству моделей** - Более 400 моделей от разных провайдеров
2. **Единый API** - Один интерфейс для всех моделей
3. **Конкуренция цен** - Разные провайдеры предлагают разные цены
4. **Гибкость** - Легко переключаться между моделями
5. **Без привязки** - Не зависите от одного провайдера

## Решение проблем

### Ошибка API ключа
Если вы получаете ошибку о недостатке API ключа, убедитесь, что:
1. Файл `.env` существует и находится в корневой директории проекта
2. Переменная `OPENROUTER_API_KEY` установлена правильно
3. Ключ скопирован полностью
4. Нет лишних пробелов в начале или конце ключа

### Ошибка модели
Если модель не работает:
1. Проверьте правильность названия модели
2. Убедитесь, что у вас есть доступ к этой модели в OpenRouter
3. Проверьте баланс вашего аккаунта OpenRouter

### Тестирование интеграции

Для тестирования интеграции OpenRouter можно использовать тестовый конфигурационный файл `test-openrouter-config.json`, который уже создан в проекте. Просто запустите:

```bash
python main.py --config test-openrouter-config.json
```

Если все настроено правильно, агент должен инициализироваться с моделью OpenRouter.