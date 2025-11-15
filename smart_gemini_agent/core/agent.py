"""
Основной класс Smart AI Agent с оптимизированной производительностью
Поддержка stdio и HTTP/SSE транспортов для MCP серверов
"""

import os
import re
import time
import asyncio
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
from ..tools.planning_tools import PlanCreateTool, PlanNextTool, PlanRunTool
from ..tools.tool_analyzer import ToolAnalyzer
from ..utils.decorators import retry_on_failure, retry_on_failure_async_gen
from ..utils.timeout import async_gen_timeout_wrapper, get_watchdog
from ..utils.constants import (
    MAX_RETRY_ATTEMPTS,
    DEFAULT_THREAD_ID,
    MAX_RECOVERY_SUGGESTIONS,
    RATE_LIMIT_HTTP_CODE,
    MAX_TOOL_REPEATS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_TOOL_TIMEOUT,
    RETRY_DELAY_PATTERN,
)
from .prompt_manager import PromptManager
from .response_formatter import ResponseFormatter
from .context_manager import SmartContextManager, ContextType
from .error_recovery import ErrorRecoverySystem

# Инициализация logger перед импортом опциональных модулей
logger = logging.getLogger(__name__)

# Новые модули v5.0
try:
    from ..observability import AgentMetrics, AgentTracer, QualityEvaluator
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    logger.warning("⚠️  Модуль observability не доступен")

try:
    from ..memory import LongTermMemory
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    logger.warning("⚠️  Модуль memory не доступен")

try:
    from ..planning import TaskPlanner
    PLANNING_AVAILABLE = True
except ImportError:
    PLANNING_AVAILABLE = False
    logger.warning("⚠️  Модуль planning не доступен")

try:
    from ..security import SecurityGuardrails
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    logger.warning("⚠️  Модуль security не доступен")


class LoopDetectedException(Exception):
    """Исключение при обнаружении зацикливания"""
    def __init__(self, tool_name: str, call_count: int):
        self.tool_name = tool_name
        self.call_count = call_count
        super().__init__(
            f"Обнаружено зацикливание: инструмент '{tool_name}' вызван {call_count} раз"
        )


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
        self.tools_map = {}
        self._initialized = False
        self._allow_loop_continuation = False  # Флаг для продолжения при зацикливании
        self._reset_checkpoint_on_next_run = False
        
        # Таймауты
        self.request_timeout = getattr(config, 'request_timeout', DEFAULT_REQUEST_TIMEOUT)
        self.tool_timeout = getattr(config, 'tool_timeout', DEFAULT_TOOL_TIMEOUT)

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
        
        # === НОВЫЕ МОДУЛИ V5.0 ===
        
        # Agent Ops: Observability
        self.metrics = None
        self.tracer = None
        self.evaluator = None
        
        if getattr(config, 'enable_observability', True) and OBSERVABILITY_AVAILABLE:
            self.metrics = AgentMetrics()
            self.tracer = AgentTracer(traces_dir=getattr(config, 'traces_dir', './traces'))
            
            if getattr(config, 'enable_evaluation', True):
                self.evaluator = QualityEvaluator()
            
            logger.info("✅ Agent Ops: Observability включена")
        
        # Долговременная память
        self.long_term_memory = None
        
        if getattr(config, 'use_long_term_memory', True) and MEMORY_AVAILABLE:
            self.long_term_memory = LongTermMemory(
                persist_directory=getattr(config, 'memory_path', './agent_memory'),
                embedding_provider=getattr(config, 'embedding_provider', 'simple')
            )
            logger.info("✅ Долговременная память включена")
        
        # Планирование (инициализируется позже после создания модели)
        self.task_planner = None
        self._enable_planning = getattr(config, 'enable_planning', True) and PLANNING_AVAILABLE
        self.current_plan = None
        
        # Безопасность (Guardrails)
        self.guardrails = None
        
        if getattr(config, 'enable_guardrails', True) and SECURITY_AVAILABLE:
            self.guardrails = SecurityGuardrails()
            logger.info("✅ Система безопасности (Guardrails) включена")

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
            elif self.config.model_provider in ["openai", "openrouter"]:
                api_key = os.getenv("OPENAI_API_KEY")
                model = ChatOpenAI(
                    model=self.config.model_name,
                    api_key=convert_to_secret_str(api_key) if api_key else None,
                    base_url=os.getenv("OPENAI_BASE_URL"),
                    temperature=self.config.temperature,
                )
                logger.info(
                    f"Используется модель OpenAI-совместимая ({self.config.model_provider}): {self.config.model_name}"
                )
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
            
            # === ИНИЦИАЛИЗАЦИЯ ПЛАНИРОВЩИКА (после создания модели) ===
            if self._enable_planning:
                self.task_planner = TaskPlanner(llm=model)
                logger.info("✅ Система планирования инициализирована")

            self._initialized = True
            logger.info("✅ Агент успешно инициализирован")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False

    @retry_on_failure()
    async def _init_mcp_client(self):
        """Инициализация MCP клиента с поддержкой stdio и HTTP/SSE транспортов"""
        logger.info("Инициализация MCP клиента...")

        # Получаем конфигурацию серверов
        mcp_config = self.config.get_mcp_config()
        
        # Логируем информацию о транспортах
        self._log_transport_info(mcp_config)

        # Временно подавить предупреждения во время инициализации
        old_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.ERROR)

        try:
            self.mcp_client = MultiServerMCPClient(mcp_config)
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
    
    def _log_transport_info(self, mcp_config: Dict[str, Any]) -> None:
        """Логирование информации о типах транспорта MCP серверов"""
        transport_stats = {"stdio": 0, "sse": 0, "streamable-http": 0}
        
        for server_name, server_config in mcp_config.items():
            transport = server_config.get("transport", "stdio")
            if transport in transport_stats:
                transport_stats[transport] += 1
            
            # Детальное логирование для HTTP транспортов
            if transport in ["sse", "streamable-http"]:
                url = server_config.get("url", "не указан")
                logger.info(f"  📡 {server_name}: {transport} транспорт ({url})")
            else:
                command = server_config.get("command", "не указан")
                logger.info(f"  💻 {server_name}: {transport} транспорт ({command})")
        
        logger.info(f"📊 Статистика транспортов: stdio={transport_stats['stdio']}, "
                   f"sse={transport_stats['sse']}, http={transport_stats['streamable-http']}")

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

        # Инструменты планирования плана задач
        plan_create_tool = PlanCreateTool(agent=self)
        plan_next_tool = PlanNextTool(agent=self)
        plan_run_tool = PlanRunTool(agent=self)

        # Добавляем к списку инструментов
        self.tools.extend([
            delete_file_tool,
            delete_dir_tool,
            plan_create_tool,
            plan_next_tool,
            plan_run_tool,
        ])

        logger.info("Добавлены локальные инструменты:")
        logger.info(f"  • {delete_file_tool.name}: {delete_file_tool.description}")
        logger.info(f"  • {delete_dir_tool.name}: {delete_dir_tool.description}")
        logger.info(f"  • {plan_create_tool.name}: {plan_create_tool.description}")
        logger.info(f"  • {plan_next_tool.name}: {plan_next_tool.description}")
        logger.info(f"  • {plan_run_tool.name}: {plan_run_tool.description}")

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
        # v5.0: инструментирование
        task_metrics = None
        tools_used_set: set[str] = set()
        active_tool_name: Optional[str] = None
        active_tool_start: Optional[float] = None
        final_response_text: Optional[str] = None
        # Трассировка
        if self.tracer:
            try:
                self.tracer.start_trace(task=user_input, metadata={"thread_id": thread_id})
            except Exception:
                pass
        # Метрики
        if self.metrics:
            try:
                task_metrics = self.metrics.start_task(task_id=f"task_{int(start_time)}")
            except Exception:
                task_metrics = None
        
        # Отслеживание повторяющихся вызовов инструментов
        tool_call_tracker: Dict[str, int] = {}

        try:
            # Создаем улучшенный контекст без системы намерений
            enhanced_input = self._create_enhanced_context(user_input)

            # Проверяем готовность агента перед выполнением
            if not self.agent:
                yield {
                    "error": "Агент не инициализирован. Попробуйте переинициализировать."
                }
                return

            effective_thread_id = thread_id
            if self.checkpointer and self._reset_checkpoint_on_next_run:
                effective_thread_id = f"{thread_id}-{int(time.time())}"
                self._reset_checkpoint_on_next_run = False

            config: RunnableConfig = {
                "configurable": {"thread_id": effective_thread_id},
                "recursion_limit": 20  # Ограничиваем рекурсию для предотвращения зависания
            }
            message_input = {"messages": [HumanMessage(content=enhanced_input)]}

            # Используем таймаут обертку для предотвращения зависаний
            stream_gen = self.agent.astream(message_input, config)
            
            async for chunk in async_gen_timeout_wrapper(
                stream_gen,
                timeout=self.request_timeout,
                per_item_timeout=self.tool_timeout,
                heartbeat_interval=10.0
            ):
                # Отслеживаем использование инструментов
                if "agent" in chunk:
                    agent_step = chunk["agent"]
                    if isinstance(agent_step, dict) and agent_step.get("messages"):
                        for msg in agent_step["messages"]:
                            if msg.tool_calls:
                                for tool_call in msg.tool_calls:
                                    tool_name = tool_call["name"]
                                    tool_used = tool_name
                                    tools_used_set.add(str(tool_name))
                                    
                                    # Отслеживаем повторяющиеся вызовы
                                    tool_call_tracker[tool_name] = tool_call_tracker.get(tool_name, 0) + 1
                                    # Трассировка span для инструмента
                                    if self.tracer and active_tool_name is None:
                                        try:
                                            self.tracer.start_span(
                                                name=f"tool:{tool_name}",
                                                attributes={"args": tool_call.get("args", {})}
                                            )
                                        except Exception:
                                            pass
                                    # Запомним старт времени для оценки длительности
                                    if active_tool_name is None:
                                        active_tool_name = tool_name
                                        active_tool_start = time.time()
                                    
                                    # Обнаружено зацикливание
                                    if tool_call_tracker[tool_name] > MAX_TOOL_REPEATS:
                                        logger.warning(
                                            f"⚠️ Инструмент '{tool_name}' вызван {tool_call_tracker[tool_name]} раз. "
                                            f"Возможно зацикливание!"
                                        )
                                        
                                        # Если не разрешено продолжение, выдаем предупреждение и останавливаемся
                                        if not self._allow_loop_continuation:
                                            # Выдаем специальное событие с предупреждением
                                            yield {
                                                "loop_warning": {
                                                    "tool_name": tool_name,
                                                    "call_count": tool_call_tracker[tool_name],
                                                    "message": (
                                                        f"Loop: {tool_name} x{tool_call_tracker[tool_name]}\n"
                                                        f"Stop | /continue | disable in mcp.json"
                                                    )
                                                }
                                            }
                                            # Останавливаем выполнение
                                            raise LoopDetectedException(tool_name, tool_call_tracker[tool_name])
                            else:
                                # Нет вызова инструмента: это может быть текстовая мысль или финальный ответ
                                try:
                                    content = getattr(msg, "content", None)
                                    if content:
                                        final_response_text = str(content)
                                except Exception:
                                    pass

                # Фиксируем завершение вызова инструмента по приходу блока tools
                if "tools" in chunk and active_tool_name:
                    # Метрики по инструменту
                    if self.metrics:
                        try:
                            duration = (time.time() - active_tool_start) if active_tool_start else 0.0
                            self.metrics.record_tool_call(active_tool_name, duration=duration, success=True)
                        except Exception:
                            pass
                    # Завершаем span
                    if self.tracer:
                        try:
                            # end_span завершит текущий span
                            if getattr(self.tracer, "current_span", None):
                                self.tracer.end_span(self.tracer.current_span)
                        except Exception:
                            pass
                    # Сбрасываем активный инструмент после фиксации метрик
                    active_tool_name = None
                    active_tool_start = None

                # Сохраняем финальный ответ для памяти
                if "__end__" in chunk:
                    try:
                        messages = chunk["__end__"].get("messages", [])
                        if messages:
                            last_message = messages[-1]
                            if hasattr(last_message, "content") and last_message.content:
                                if isinstance(last_message.content, list):
                                    final_response_text = "\n".join(map(str, last_message.content))
                                else:
                                    final_response_text = str(last_message.content)
                    except Exception:
                        pass
                yield chunk

        except TimeoutError as e:
            # Обработка таймаута
            success = False
            error_message = str(e)
            logger.error(f"⏱️ Timeout: {error_message}")
            yield {
                "error": (
                    f"⏱️ Timeout: операция заняла более {self.request_timeout}с\n"
                    f"Fix: упростите запрос | отключите медленные инструменты в mcp.json"
                )
            }
        except asyncio.CancelledError:
            # Операция прервана пользователем (Ctrl+C)
            logger.info("🛑 Операция прервана пользователем")
            yield {"error": "🛑 Операция прервана пользователем (Ctrl+C)"}
        except ResourceExhausted as e:
            error_text = str(e)
            retry_secs = None
            m = RETRY_DELAY_PATTERN.search(error_text)
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
                    f"Rate limit (429). {wait_hint}"
                )
            else:
                friendly_error = (
                    f"Rate limit {self.config.model_provider} (429). {wait_hint}"
                )
            yield {"error": friendly_error}
        except LoopDetectedException as e:
            # Обработка зацикливания
            success = False
            error_message = str(e)
            logger.error(f"Loop stopped: {error_message}")
            self._reset_checkpoint_on_next_run = True
            yield {
                "error": (
                    f"Stopped: {error_message}\n"
                    f"Fix: rephrase | disable {e.tool_name} | /continue"
                )
            }
        except Exception as e:
            # Обрабатываем ошибки OpenRouter отдельно
            error_text = str(e).lower()
            if "rate limit" in error_text or RATE_LIMIT_HTTP_CODE in error_text:
                friendly_error = f"Rate limit {self.config.model_provider} (429). Wait & retry."
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
            try:
                if (
                    "tool_calls" in str(e)
                    and ("toolmessage" in str(e).lower() or "validate_chat_history" in str(e).lower())
                ):
                    self._reset_checkpoint_on_next_run = True
            except Exception:
                pass
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
            # Завершение метрик по задаче
            if self.metrics and task_metrics:
                try:
                    quality_score = None
                    eval_text = final_response_text
                    if not eval_text and success:
                        if tools_used_set:
                            tool_list = ", ".join(sorted(tools_used_set))
                            eval_text = (
                                f"Задача выполнена успешно. Использованы инструменты: {tool_list}. "
                                f"Время выполнения: {execution_time:.1f}с."
                            )
                        else:
                            eval_text = "Задача выполнена успешно."
                    if self.evaluator and eval_text:
                        try:
                            eval_result = await self.evaluator.evaluate_response(
                                task=user_input,
                                response=eval_text,
                            )
                            quality_score = getattr(eval_result, "overall_score", None)
                        except Exception:
                            quality_score = None
                    self.metrics.complete_task(
                        task_metrics,
                        success=success,
                        error_type=(error_message.split(':')[0] if error_message else None),
                        quality_score=quality_score,
                    )
                except Exception:
                    pass
            # Завершение трассировки
            if self.tracer:
                try:
                    self.tracer.end_trace()
                except Exception:
                    pass
            # Сохранение в долговременную память
            if self.long_term_memory and final_response_text:
                try:
                    await self.long_term_memory.remember(
                        interaction_type="chat",
                        user_input=user_input,
                        agent_response=final_response_text,
                        tools_used=list(tools_used_set),
                        success=success,
                        metadata={"thread_id": thread_id},
                    )
                except Exception:
                    pass

    def _create_enhanced_context(self, user_input: str) -> str:
        """Создание улучшенного контекста без системы намерений"""
        base_context = f"DIR: {self.config.filesystem_path}"

        # Краткая сводка постоянных данных (если есть)
        pdata = self.context_manager.get_persistent_data_summary()
        context_info = []
        if pdata.get("stored_users"):
            user_list = pdata.get("user_list", [])
            if user_list:
                context_info.append(f"USERS: {', '.join(user_list[:5])}")
        last_chat = pdata.get("last_entities", {}).get("chat")
        if last_chat:
            context_info.append(f"CHAT: {last_chat}")
        if pdata.get("stored_files"):
            context_info.append(f"FILES: {pdata.get('stored_files', 0)}")

        context_section = " | ".join(context_info) if context_info else ""

        parts = [base_context]
        if context_section:
            parts.append(context_section)
        parts.append(user_input)

        return " | ".join(parts)





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
            # v5.0 features
            "v5_features": {
                "observability_enabled": self.metrics is not None,
                "long_term_memory_enabled": self.long_term_memory is not None,
                "planning_enabled": self.task_planner is not None,
                "guardrails_enabled": self.guardrails is not None,
            },
        }

    def reload_prompt(self) -> str:
        """Перезагрузка промпта из файла"""
        return self.prompt_manager.reload_prompt()

    def switch_prompt(self, new_prompt_file: str) -> bool:
        """Переключение на новый файл промпта"""
        # Обновляем конфигурацию
        from ..utils.config_updater import ConfigUpdater

        updater = ConfigUpdater()
        if updater.update_prompt_file(new_prompt_file):
            # Перезагружаем промпт
            self.config.prompt_file = new_prompt_file
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
    
    # === НОВЫЕ МЕТОДЫ V5.0 ===
    
    def get_metrics_summary(self) -> Optional[Dict[str, Any]]:
        """Получение сводки метрик агента"""
        if self.metrics:
            return self.metrics.get_summary()
        return None
    
    def print_metrics(self):
        """Вывод метрик в консоль"""
        if self.metrics:
            self.metrics.print_summary()
        else:
            logger.warning("⚠️  Метрики не включены")
    
    def get_recent_traces(self, count: int = 5) -> List:
        """Получение последних трассировок"""
        if self.tracer:
            return self.tracer.get_recent_traces(count)
        return []
    
    def print_trace(self, trace_id: Optional[str] = None):
        """Вывод трассировки в консоль"""
        if self.tracer:
            if trace_id:
                self.tracer.print_trace(trace_id)
            elif self.tracer.current_trace:
                self.tracer.print_trace(self.tracer.current_trace.trace_id)
        else:
            logger.warning("⚠️  Трассировка не включена")
    
    def get_memory_statistics(self) -> Optional[Dict]:
        """Получение статистики долговременной памяти"""
        if self.long_term_memory:
            return self.long_term_memory.get_statistics()
        return None
    
    async def search_memory(self, query: str, k: int = 5) -> List:
        """Поиск в долговременной памяти"""
        if self.long_term_memory:
            return await self.long_term_memory.recall_similar(query, k=k)
        return []
    
    def clear_long_term_memory(self):
        """Очистка долговременной памяти"""
        if self.long_term_memory:
            self.long_term_memory.clear()
            logger.info("🗑️  Долговременная память очищена")
        else:
            logger.warning("⚠️  Долговременная память не включена")
    
    async def create_task_plan(self, task: str) -> Optional[Any]:
        """Создание плана для сложной задачи"""
        if self.task_planner:
            plan = await self.task_planner.create_execution_plan(task)
            self.current_plan = plan
            return plan
        else:
            logger.warning("⚠️  Система планирования не включена")
            return None
    
    def get_security_statistics(self) -> Optional[Dict]:
        """Получение статистики системы безопасности"""
        if self.guardrails:
            return self.guardrails.get_statistics()
        return None
    
    def update_security_policy(self, key: str, value: Any):
        """Обновление политики безопасности"""
        if self.guardrails:
            self.guardrails.update_policy(key, value)
        else:
            logger.warning("⚠️  Система безопасности не включена")

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

    def enable_loop_continuation(self):
        """Включить режим игнорирования зацикливания"""
        self._allow_loop_continuation = True
        logger.info("✅ Режим игнорирования зацикливания включен")
        self._reset_checkpoint_on_next_run = True
        return "✅ Режим игнорирования зацикливания включен. Следующий запрос будет выполнен без остановки на повторяющихся вызовах инструментов."

    def disable_loop_continuation(self):
        """Выключить режим игнорирования зацикливания"""
        self._allow_loop_continuation = False
        self._reset_checkpoint_on_next_run = False
        logger.info("❌ Режим игнорирования зацикливания выключен")
        return "❌ Режим игнорирования зацикливания выключен. Агент будет останавливаться при обнаружении зацикливания."

    def get_loop_continuation_status(self) -> bool:
        """Получить статус режима игнорирования зацикливания"""
        return self._allow_loop_continuation

    def set_current_plan(self, plan: Any) -> None:
        self.current_plan = plan

    def get_current_plan(self) -> Optional[Any]:
        return self.current_plan

    async def execute_next_task(self) -> Dict[str, Any]:
        if not self.task_planner or not self.current_plan:
            return {"error": "Нет активного плана или планировщик отключен"}
        try:
            from ..planning.task_planner import TaskStatus as PlanTaskStatus
        except Exception:
            return {"error": "Планировщик недоступен"}
        next_task = self.current_plan.get_next_task()
        if not next_task:
            return {"message": "Нет готовых к выполнению подзадач"}
        next_task.status = PlanTaskStatus.IN_PROGRESS
        exec_res = await self._execute_text_step(next_task.description)
        if exec_res.get("success"):
            next_task.status = PlanTaskStatus.COMPLETED
            next_task.result = exec_res.get("final_response")
            return {"completed": True, "task_id": next_task.id}
        else:
            next_task.status = PlanTaskStatus.FAILED
            next_task.error = exec_res.get("error")
            return {"completed": False, "task_id": next_task.id, "error": next_task.error}

    async def run_plan(self) -> Dict[str, Any]:
        if not self.task_planner or not self.current_plan:
            return {"error": "Нет активного плана или планировщик отключен"}
        completed = 0
        failed = 0
        failed_retry_attempts = 0
        max_failed_retries = 1
        while True:
            res = await self.execute_next_task()
            if "message" in res and res["message"]:
                if self._allow_loop_continuation and failed_retry_attempts < max_failed_retries:
                    try:
                        from ..planning.task_planner import TaskStatus as PlanTaskStatus
                        failed_task = next((t for t in self.current_plan.subtasks if t.status == PlanTaskStatus.FAILED), None)
                    except Exception:
                        failed_task = None
                    if failed_task is not None:
                        try:
                            failed_task.status = PlanTaskStatus.PENDING
                            failed_retry_attempts += 1
                            continue
                        except Exception:
                            pass
                break
            if res.get("completed") is True:
                completed += 1
            elif res.get("completed") is False:
                failed += 1
            else:
                break
        prog = self.current_plan.get_progress() if hasattr(self.current_plan, "get_progress") else {}
        return {"completed_count": completed, "failed_count": failed, "progress": prog}

    async def _execute_text_step(self, text: str) -> Dict[str, Any]:
        final_response = None
        error_msg = None
        try:
            async for chunk in self.process_message(text, thread_id="plan"):
                if "error" in chunk:
                    error_msg = chunk["error"]
                    break
                if "agent" in chunk:
                    agent_step = chunk["agent"]
                    if isinstance(agent_step, dict) and agent_step.get("messages"):
                        for msg in agent_step["messages"]:
                            try:
                                content = getattr(msg, "content", None)
                                if content:
                                    final_response = str(content)
                            except Exception:
                                pass
                if "__end__" in chunk:
                    try:
                        messages = chunk["__end__"].get("messages", [])
                        if messages:
                            last_message = messages[-1]
                            if hasattr(last_message, "content") and last_message.content:
                                final_response = str(last_message.content)
                    except Exception:
                        pass
        except Exception as e:
            error_msg = str(e)
        return {"success": error_msg is None, "final_response": final_response, "error": error_msg}

    async def cleanup(self):
        """Корректное закрытие агента и всех ресурсов"""
        logger.info("🧹 Начало cleanup агента...")
        
        try:
            # === CLEANUP НОВЫХ МОДУЛЕЙ V5.0 ===
            
            # Экспорт метрик и трассировок перед завершением
            if self.metrics:
                try:
                    self.metrics.print_summary()
                    logger.info("✅ Метрики сохранены")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка сохранения метрик: {e}")
            
            if self.tracer and self.tracer.current_trace:
                try:
                    self.tracer.end_trace()
                    logger.info("✅ Трассировка завершена")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка завершения трассировки: {e}")
            
            if self.guardrails:
                try:
                    stats = self.guardrails.get_statistics()
                    if isinstance(stats, dict):
                        total_validations = stats.get("total_validations")
                        blocked_actions = stats.get("blocked_actions")
                        logger.info(
                            f"🛡️ Безопасность: проверено {total_validations}, заблокировано {blocked_actions}"
                        )
                    else:
                        logger.info(f"🛡️ Безопасность: статистика безопасности: {stats}")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка получения статистики безопасности: {e}")
            
            # Закрываем MCP клиент
            if self.mcp_client:
                try:
                    # Проверяем есть ли метод close или aclose
                    if hasattr(self.mcp_client, 'aclose'):
                        await self.mcp_client.aclose()
                    elif hasattr(self.mcp_client, 'close'):
                        if asyncio.iscoroutinefunction(self.mcp_client.close):
                            await self.mcp_client.close()
                        else:
                            self.mcp_client.close()
                    logger.info("✅ MCP клиент закрыт")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при закрытии MCP клиента: {e}")
            
            # Очищаем контекст
            if self.context_manager:
                self.context_manager.clear_context(keep_stats=True)
                logger.info("✅ Контекст очищен")
            
            logger.info("✅ Cleanup завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при cleanup: {e}")
        finally:
            # Гарантированно переводим агент в неинициализированное состояние
            self._initialized = False
            self.agent = None
            self.mcp_client = None
            self.checkpointer = None
            self.tools = []
            self.tools_map = {}
            self.current_plan = None
