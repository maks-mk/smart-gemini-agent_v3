"""
Основной класс Smart AI Agent с оптимизированной производительностью
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator, cast
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from google.api_core.exceptions import ResourceExhausted
from langchain_core.utils import convert_to_secret_str
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_core.runnables.config import RunnableConfig
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

from ..config.agent_config import AgentConfig
from ..tools.delete_tools import SafeDeleteFileTool, SafeDeleteDirectoryTool
from ..tools.tool_analyzer import ToolAnalyzer
from ..utils.decorators import retry_on_failure, retry_on_failure_async_gen
from .prompt_manager import PromptManager
from .response_formatter import ResponseFormatter
from .context_manager import SmartContextManager, ContextType
from .error_recovery import ErrorRecoverySystem

logger = logging.getLogger(__name__)

# Константы для производительности
MAX_RETRY_ATTEMPTS = 2
DEFAULT_THREAD_ID = "default"
MAX_RECOVERY_SUGGESTIONS = 3
RATE_LIMIT_HTTP_CODE = "429"

# Предкомпилированные регулярные выражения
_RETRY_DELAY_PATTERN = re.compile(r"retry_delay\s*{\s*seconds:\s*(\d+)")


class FileSystemAgent:
    """
    Умный AI-агент для работы с файловой системой на базе Google Gemini или OpenRouter
    с поддержкой Model Context Protocol (MCP)
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent = None
        self.checkpointer = None
        self.mcp_client = None
        self.tools: List[BaseTool] = []
        self._initialized = False

        # Инициализируем компоненты
        self.tool_analyzer = ToolAnalyzer()
        self.context_manager = SmartContextManager(
            max_entries=config.max_context_files * 2,
            debug_mode=getattr(config, 'debug_mode', False),
        )
        self.error_recovery = ErrorRecoverySystem(
            context_manager=self.context_manager,
            debug_mode=getattr(config, 'debug_mode', False),
        )
        self.prompt_manager = PromptManager(config)
        self.response_formatter = ResponseFormatter(
            debug_mode=getattr(config, 'debug_mode', False)
        )

        logger.info(f"Создан умный агент с {config.model_provider}")
        logger.info(f"Рабочая директория: {config.filesystem_path}")

    @property
    def is_ready(self) -> bool:
        """Проверяет готовность агента"""
        return self._initialized and self.agent is not None

    async def initialize(self) -> bool:
        """Инициализация агента"""
        if self._initialized:
            logger.warning("Агент уже инициализирован")
            return True

        logger.info("Инициализация агента...")

        try:
            self.config.validate()
            await self._init_mcp_client()

            # Создание модели в зависимости от провайдера
            if self.config.model_provider == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                model = ChatGoogleGenerativeAI(
                    model=self.config.model_name,
                    google_api_key=convert_to_secret_str(api_key) if api_key else None,
                    temperature=self.config.temperature,
                )
                logger.info(f"Используется модель Gemini: {self.config.model_name}")
            elif self.config.model_provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY")
                model = ChatOpenAI(
                    model=self.config.model_name,
                    api_key=convert_to_secret_str(api_key) if api_key else None,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=self.config.temperature,
                )
                logger.info(f"Используется модель OpenRouter: {self.config.model_name}")
            else:
                raise ValueError(
                    f"Неподдерживаемый провайдер модели: {self.config.model_provider}"
                )

            if self.config.use_memory:
                self.checkpointer = InMemorySaver()
                logger.info("Память агента включена")

            # Обновляем анализатор инструментов в менеджере промптов
            self.prompt_manager.update_tool_analyzer(self.tool_analyzer)

            self.agent = create_react_agent(
                model=model,
                tools=self.tools,
                checkpointer=self.checkpointer,
                prompt=self.prompt_manager.get_system_prompt(),
            )

            self._initialized = True
            logger.info("✅ Агент успешно инициализирован")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False

    @retry_on_failure()
    async def _init_mcp_client(self):
        """Инициализация MCP клиента"""
        logger.info("Инициализация MCP клиента...")

        # Временно подавить предупреждения во время инициализации
        old_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.ERROR)

        try:
            self.mcp_client = MultiServerMCPClient(self.config.get_mcp_config())
            self.tools = await self.mcp_client.get_tools()
        finally:
            # Восстановить уровень логирования
            logging.getLogger().setLevel(old_level)

        if not self.tools:
            raise Exception("Нет доступных MCP инструментов")

        # Добавляем локальные инструменты для удаления
        self._add_local_tools()

        # Анализируем и категоризируем инструменты
        self.tools_map = self.tool_analyzer.analyze_tools(self.tools)

        logger.info(f"Загружено {len(self.tools)} инструментов")
        for tool in self.tools:
            logger.info(f"  • {tool.name}")

    def _add_local_tools(self):
        """Добавление локальных инструментов"""
        # Проверяем, что filesystem_path не None
        if not self.config.filesystem_path:
            logger.warning(
                "Не удалось добавить локальные инструменты: filesystem_path не указан"
            )
            return

        # Создаем локальные инструменты для удаления
        delete_file_tool = SafeDeleteFileTool(
            working_directory=cast(Path, self.config.filesystem_path)
        )
        delete_dir_tool = SafeDeleteDirectoryTool(
            working_directory=cast(Path, self.config.filesystem_path)
        )

        # Добавляем к списку инструментов
        self.tools.extend([delete_file_tool, delete_dir_tool])

        logger.info("Добавлены локальные инструменты:")
        logger.info(f"  • {delete_file_tool.name}: {delete_file_tool.description}")
        logger.info(f"  • {delete_dir_tool.name}: {delete_dir_tool.description}")

    @retry_on_failure_async_gen()
    async def process_message(
        self, user_input: str, thread_id: str = "default"
    ) -> AsyncGenerator[Dict, None]:
        """Умная обработка сообщения пользователя со стримингом шагов"""
        if not self.is_ready:
            yield {"error": "Агент не готов. Попробуйте переинициализировать."}
            return

        start_time = time.time()
        intent = "auto"
        params: Dict[str, Any] = {"raw_input": user_input}
        tool_used = None
        success = True
        error_message = None

        try:
            # Создаем улучшенный контекст без системы намерений
            enhanced_input = self._create_enhanced_context(user_input)

            # Проверяем готовность агента перед выполнением
            if not self.agent:
                yield {
                    "error": "Агент не инициализирован. Попробуйте переинициализировать."
                }
                return

            config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
            message_input = {"messages": [HumanMessage(content=enhanced_input)]}

            async for chunk in self.agent.astream(message_input, config):
                # Отслеживаем использование инструментов
                if "agent" in chunk:
                    agent_step = chunk["agent"]
                    if isinstance(agent_step, dict) and agent_step.get("messages"):
                        for msg in agent_step["messages"]:
                            if msg.tool_calls:
                                for tool_call in msg.tool_calls:
                                    tool_used = tool_call["name"]

                yield chunk

        except ResourceExhausted as e:
            error_text = str(e)
            retry_secs = None
            m = _RETRY_DELAY_PATTERN.search(error_text)
            if m:
                retry_secs = int(m.group(1))

            wait_hint = (
                f"Пожалуйста, подождите примерно {retry_secs} секунд и повторите попытку."
                if retry_secs
                else "Пожалуйста, подождите немного и повторите попытку."
            )

            # Улучшенное сообщение об ошибке, которое учитывает провайдера модели
            if self.config.model_provider == "gemini":
                friendly_error = (
                    f"😔 **Превышены лимиты API Google Gemini (ошибка 429)**\n\n"
                    f"{wait_hint}\n\n"
                    f"Подробнее о квотах: https://ai.google.dev/gemini-api/docs/rate-limits"
                )
            else:
                friendly_error = (
                    f"😔 **Превышены лимиты API {self.config.model_provider.capitalize()} (ошибка 429)**\n\n"
                    f"{wait_hint}"
                )
            yield {"error": friendly_error}
        except Exception as e:
            # Обрабатываем ошибки OpenRouter отдельно
            error_text = str(e).lower()
            if "rate limit" in error_text or RATE_LIMIT_HTTP_CODE in error_text:
                friendly_error = (
                    f"😔 **Превышены лимиты API {self.config.model_provider.capitalize()} (ошибка 429)**\n\n"
                    f"Пожалуйста, подождите немного и повторите попытку."
                )
                yield {"error": friendly_error}
                return

            success = False
            error_message = str(e)

            # Анализируем ошибку и пытаемся восстановиться
            error_context = {
                "intent": intent,
                "params": params,
                "user_input": user_input,
            }

            error_type, recovery_actions = self.error_recovery.analyze_error(
                error_message, error_context
            )

            if recovery_actions and getattr(self.config, 'debug_mode', False):
                logger.info(
                    f"🔧 Найдены стратегии восстановления для ошибки {error_type.value}:"
                )
                for action in recovery_actions[:MAX_RECOVERY_SUGGESTIONS]:
                    logger.info(f"  • {action.description}")

            # Формируем улучшенное сообщение об ошибке с предложениями
            final_error_msg = self._format_enhanced_error(
                error_message, error_type, recovery_actions
            )

            logger.error(f"❌ Ошибка обработки: {error_message}")
            import traceback

            logger.error(f"Трассировка: {traceback.format_exc()}")
            yield {"error": final_error_msg}

        finally:
            # Записываем операцию в контекст
            execution_time = time.time() - start_time
            self.context_manager.add_context(
                context_type=ContextType.USER_ACTION,
                intent=intent,
                params=params,
                success=success,
                error_message=error_message,
                tool_used=tool_used,
                execution_time=execution_time,
            )

    def _create_enhanced_context(self, user_input: str) -> str:
        """Создание улучшенного контекста без системы намерений"""
        base_context = f"Рабочая директория: '{self.config.filesystem_path}'"

        # Краткая сводка постоянных данных (если есть)
        pdata = self.context_manager.get_persistent_data_summary()
        context_info = []
        if pdata.get("stored_users"):
            context_info.append(f"ИЗВЕСТНЫЕ ПОЛЬЗОВАТЕЛИ: {pdata['user_list']}")
        last_chat = pdata.get("last_entities", {}).get("chat")
        if last_chat:
            context_info.append(f"ПОСЛЕДНИЙ ЧАТ: {last_chat}")
        if pdata.get("stored_files"):
            context_info.append("ИЗВЕСТНЫЕ ФАЙЛЫ ДОСТУПНЫ (сокр. список)")

        context_section = "\n".join(context_info) if context_info else ""

        instruction = (
            "ЗАДАЧА: Выполни запрос пользователя, самостоятельно выбирая подходящие инструменты."
        )

        enhanced_context = f"""
{base_context}

{instruction}

{context_section}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}
"""

        return enhanced_context.strip()





    def get_status(self) -> Dict[str, Any]:
        """Информация о состоянии умного агента"""
        tools_by_category = {k: len(v) for k, v in self.tools_map.items() if v}
        performance_insights = self.context_manager.get_performance_insights()
        last_ctx = self.context_manager.get_last_context()

        return {
            "initialized": self._initialized,
            "ready": self.is_ready,
            "model_name": self.config.model_name,
            "temperature": self.config.temperature,
            "use_memory": self.config.use_memory,
            "working_directory": self.config.filesystem_path,
            "total_tools": len(self.tools),
            "tools_by_category": tools_by_category,
            "context_memory_items": performance_insights.get("total_operations", 0),
            "last_action": getattr(last_ctx, "intent", None),
            "performance_insights": performance_insights,
            "intelligence_features": [
                "Smart Context Management",
                "Tool Usage Optimization",
                "Performance Analytics",
                "Error Pattern Recognition",
                "Intelligent Error Recovery",
                "Universal MCP Support",
            ],
            "error_recovery_stats": self.error_recovery.get_error_statistics(),
        }

    def reload_prompt(self) -> str:
        """Перезагрузка промпта из файла"""
        return self.prompt_manager.reload_prompt()

    def switch_prompt(self, new_prompt_file: str) -> bool:
        """Переключение на новый файл промпта"""
        if self.prompt_manager.update_prompt_file(new_prompt_file):
            # Обновляем конфигурацию
            from ..utils.config_updater import ConfigUpdater

            updater = ConfigUpdater()
            updater.update_prompt_file(new_prompt_file)

            # Перезагружаем промпт
            self.reload_prompt()
            logger.info(f"Промпт переключен на: {new_prompt_file}")
            return True
        return False

    def get_available_prompts(self) -> list[str]:
        """Получение списка доступных промптов"""
        return self.prompt_manager.get_available_prompts()

    def clear_context_memory(self):
        """Очистка контекстной памяти"""
        self.context_manager.clear_context(keep_stats=True)
        logger.info("Контекстная память очищена")

    def get_context_insights(self) -> Dict[str, Any]:
        """Получение аналитики контекста"""
        context_insights = self.context_manager.get_performance_insights()
        error_insights = self.error_recovery.get_error_statistics()

        return {
            **context_insights,
            "error_insights": error_insights,
        }

    def export_context(self, format_type: str = "json") -> str:
        """Экспорт контекста агента"""
        return self.context_manager.export_context(format_type)

    def get_tools_by_category(self, category: str) -> List:
        """Получение инструментов по категории"""
        return self.tools_map.get(category, [])

    def get_available_categories(self) -> List[str]:
        """Получение списка доступных категорий инструментов"""
        return [cat for cat, tools in self.tools_map.items() if tools]

    def _format_enhanced_error(
        self, error_message: str, error_type, recovery_actions: List
    ) -> str:
        """Форматирование улучшенного сообщения об ошибке с предложениями восстановления"""
        enhanced_msg = f"❌ **Ошибка**: {error_message}\n\n"

        if recovery_actions:
            enhanced_msg += "💡 **Предложения по решению:**\n"
            for i, action in enumerate(recovery_actions[:MAX_RECOVERY_SUGGESTIONS], 1):
                enhanced_msg += f"{i}. {action.description}\n"

            enhanced_msg += (
                "\n🔄 Попробуйте переформулировать запрос или уточнить детали."
            )
        else:
            enhanced_msg += (
                "🔄 Попробуйте переформулировать запрос или обратитесь за помощью."
            )

        return enhanced_msg
