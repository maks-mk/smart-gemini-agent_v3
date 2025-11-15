"""
Система безопасности (Guardrails) для агента
Детерминированные правила и LLM-based валидация
"""

import logging
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Типы действий агента"""
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    EXECUTE_COMMAND = "execute_command"
    WEB_SEARCH = "web_search"
    API_CALL = "api_call"
    PURCHASE = "purchase"
    SEND_EMAIL = "send_email"
    GENERIC = "generic"
    EXECUTE_PLAN = "execute_plan"


@dataclass
class ValidationResult:
    """Результат валидации действия"""
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    risk_level: str = "low"  # low, medium, high
    metadata: Dict[str, Any] = None


class SecurityGuardrails:
    """
    Система безопасности для агента
    
    Согласно agents.md:
    "Лучшей практикой является гибридный подход глубокой защиты.
    Первый уровень состоит из традиционных детерминированных ограждений"
    
    Реализует:
    1. Детерминированные правила (жесткие ограничения)
    2. LLM-based валидацию (контекстная проверка)
    3. Human-in-the-Loop для критичных операций
    """
    
    def __init__(
        self,
        policies: Optional[Dict] = None,
        guard_model=None,
        enable_hitl: bool = True
    ):
        self.policies = policies or self._default_policies()
        self.guard_model = guard_model
        self.enable_hitl = enable_hitl
        
        # Счетчики
        self.total_validations = 0
        self.blocked_actions = 0
        self.confirmed_actions = 0
        self.confirmation_handler = None
        
        logger.info("✅ SecurityGuardrails инициализированы")
    
    def _default_policies(self) -> Dict:
        """Политики безопасности по умолчанию"""
        return {
            "max_file_size_mb": 100,
            "allowed_file_extensions": [
                ".txt", ".md", ".json", ".yaml", ".yml",
                ".py", ".js", ".html", ".css", ".xml"
            ],
            "blocked_paths": [
                "/etc", "/sys", "/proc", "C:\\Windows\\System32"
            ],
            "max_command_length": 500,
            "require_confirmation": {
                "delete": True,
                "purchase": True,
                "send_email": True,
                "execute_command": True,
                "execute_plan": False
            },
            "max_purchase_amount": 100.0  # USD
        }
    
    async def validate_action(
        self,
        action_type: ActionType,
        parameters: Dict[str, Any],
        context: Optional[str] = None
    ) -> ValidationResult:
        """
        Валидация действия перед выполнением
        
        Args:
            action_type: Тип действия
            parameters: Параметры действия
            context: Контекст выполнения
        """
        self.total_validations += 1
        
        # 1. Детерминированные правила
        deterministic_result = self._validate_deterministic(
            action_type, parameters
        )
        
        if not deterministic_result.allowed:
            self.blocked_actions += 1
            logger.warning(f"🚫 Действие заблокировано: {deterministic_result.reason}")
            return deterministic_result
        
        # 2. LLM-based валидация (если модель доступна)
        if self.guard_model:
            llm_result = await self._validate_with_llm(
                action_type, parameters, context
            )
            
            if not llm_result.allowed:
                self.blocked_actions += 1
                logger.warning(f"🚫 Действие заблокировано LLM: {llm_result.reason}")
                return llm_result
        
        # 3. Проверка необходимости подтверждения
        if self._requires_confirmation(action_type):
            deterministic_result.requires_confirmation = True
            logger.info(f"⚠️  Действие требует подтверждения: {action_type.value}")
        
        return deterministic_result
    
    def _validate_deterministic(
        self,
        action_type: ActionType,
        parameters: Dict[str, Any]
    ) -> ValidationResult:
        """Детерминированная валидация (жесткие правила)"""
        
        # Валидация по типам действий
        if action_type == ActionType.DELETE_FILE:
            return self._validate_delete_file(parameters)
        
        elif action_type == ActionType.WRITE_FILE:
            return self._validate_write_file(parameters)
        
        elif action_type == ActionType.EXECUTE_COMMAND:
            return self._validate_command(parameters)
        
        elif action_type == ActionType.PURCHASE:
            return self._validate_purchase(parameters)
        
        elif action_type == ActionType.EXECUTE_PLAN:
            return self._validate_execute_plan(parameters)
        
        else:
            # Для других действий - разрешено по умолчанию
            return ValidationResult(
                allowed=True,
                reason="Действие разрешено",
                risk_level="low"
            )
    
    def _validate_delete_file(self, params: Dict) -> ValidationResult:
        """Валидация удаления файла"""
        file_path = params.get('path', '')
        
        # Проверка на системные пути
        for blocked_path in self.policies['blocked_paths']:
            if blocked_path.lower() in file_path.lower():
                return ValidationResult(
                    allowed=False,
                    reason=f"Удаление файлов в {blocked_path} запрещено",
                    risk_level="high"
                )
        
        return ValidationResult(
            allowed=True,
            reason="Удаление разрешено",
            requires_confirmation=True,
            risk_level="medium"
        )
    
    def _validate_write_file(self, params: Dict) -> ValidationResult:
        """Валидация записи файла"""
        file_path = params.get('path', '')
        size_mb = params.get('size_mb', 0)
        
        # Проверка размера
        if size_mb > self.policies['max_file_size_mb']:
            return ValidationResult(
                allowed=False,
                reason=f"Размер файла превышает лимит ({self.policies['max_file_size_mb']}MB)",
                risk_level="medium"
            )
        
        # Проверка расширения
        import os
        ext = os.path.splitext(file_path)[1].lower()
        if ext and ext not in self.policies['allowed_file_extensions']:
            return ValidationResult(
                allowed=False,
                reason=f"Расширение файла {ext} не разрешено",
                risk_level="medium"
            )
        
        return ValidationResult(
            allowed=True,
            reason="Запись разрешена",
            risk_level="low"
        )
    
    def _validate_command(self, params: Dict) -> ValidationResult:
        """Валидация выполнения команды"""
        command = params.get('command', '')
        
        # Проверка длины
        if len(command) > self.policies['max_command_length']:
            return ValidationResult(
                allowed=False,
                reason="Команда слишком длинная",
                risk_level="high"
            )
        
        # Проверка на опасные команды
        dangerous_commands = [
            'rm -rf', 'del /f', 'format', 'mkfs',
            'dd if=', ':(){ :|:& };:'  # Fork bomb
        ]
        
        for dangerous in dangerous_commands:
            if dangerous in command.lower():
                return ValidationResult(
                    allowed=False,
                    reason=f"Команда содержит опасную операцию: {dangerous}",
                    risk_level="high"
                )
        
        return ValidationResult(
            allowed=True,
            reason="Команда разрешена",
            requires_confirmation=True,
            risk_level="medium"
        )
    
    def _validate_purchase(self, params: Dict) -> ValidationResult:
        """Валидация покупки"""
        amount = params.get('amount', 0.0)
        
        if amount > self.policies['max_purchase_amount']:
            return ValidationResult(
                allowed=False,
                reason=f"Сумма покупки превышает лимит (${self.policies['max_purchase_amount']})",
                requires_confirmation=True,
                risk_level="high"
            )
        
        return ValidationResult(
            allowed=True,
            reason="Покупка в пределах лимита",
            requires_confirmation=True,
            risk_level="medium"
        )
    
    def _validate_execute_plan(self, params: Dict) -> ValidationResult:
        """Валидация выполнения плана"""
        mode = params.get("mode", "run")
        subtasks_total = int(params.get("subtasks_total", 0) or 0)
        steps = int(params.get("steps", subtasks_total) or 0)

        # По умолчанию выполнение плана разрешено, но считается усилием повышенного риска
        risk_level = "medium"
        requires_confirmation = False
        reason = "Выполнение плана"

        if mode == "run":
            # Полный запуск плана всегда требует повышенного внимания
            requires_confirmation = True
            risk_level = "high" if subtasks_total > 5 else "medium"
            reason = f"Полный запуск плана на {subtasks_total} подзадач"
        else:
            # Пошаговый режим: считаем более безопасным, но много шагов подряд всё равно рискованно
            if steps > 1 or subtasks_total > 5:
                requires_confirmation = True
                risk_level = "medium"
                reason = f"Выполнение {steps} шагов плана (всего {subtasks_total})"

        return ValidationResult(
            allowed=True,
            reason=reason,
            requires_confirmation=requires_confirmation,
            risk_level=risk_level,
        )
    
    async def _validate_with_llm(
        self,
        action_type: ActionType,
        parameters: Dict,
        context: Optional[str]
    ) -> ValidationResult:
        """Валидация с помощью LLM (Guard Model)"""
        
        validation_prompt = f"""
Ты - система безопасности AI-агента. Оцени безопасность следующего действия.

Тип действия: {action_type.value}
Параметры: {parameters}
Контекст: {context or 'отсутствует'}

Проанализируй:
1. Может ли это действие нанести вред?
2. Есть ли риски для безопасности или конфиденциальности?
3. Соответствует ли действие намерениям пользователя?

Ответь в формате JSON:
{{
    "safe": true/false,
    "reason": "объяснение",
    "risk_level": "low/medium/high"
}}
"""
        
        try:
            response = await self.guard_model.ainvoke(validation_prompt)
            
            # Парсинг ответа
            import json
            import re
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            
            if json_match:
                data = json.loads(json_match.group())
                
                return ValidationResult(
                    allowed=data.get('safe', True),
                    reason=data.get('reason', 'Проверено LLM'),
                    risk_level=data.get('risk_level', 'low')
                )
            
        except Exception as e:
            logger.error(f"Ошибка LLM валидации: {e}")
        
        # В случае ошибки - разрешаем (fail-open)
        return ValidationResult(
            allowed=True,
            reason="LLM валидация недоступна",
            risk_level="unknown"
        )
    
    def _requires_confirmation(self, action_type: ActionType) -> bool:
        """Проверка необходимости подтверждения"""
        if not self.enable_hitl:
            return False
        
        action_str = action_type.value
        
        # Проверяем в политиках
        for key, requires in self.policies['require_confirmation'].items():
            if key in action_str and requires:
                return True
        
        return False
    
    async def request_confirmation(
        self,
        action_description: str,
        risk_level: str
    ) -> bool:
        """
        Запрос подтверждения у пользователя (HITL)
        
        В реальной реализации это должно быть интерактивно
        """
        logger.warning(f"⚠️  Требуется подтверждение: {action_description}")
        logger.warning(f"Уровень риска: {risk_level}")
        
        # TODO: Реализовать интерактивный запрос
        # Сейчас просто логируем
        handler = getattr(self, "confirmation_handler", None)
        if handler:
            try:
                result = await handler(action_description, risk_level)
            except Exception as e:
                logger.warning(f"Ошибка обработчика подтверждения: {e}")
                return False
            if result:
                self.confirmed_actions += 1
                return True
            return False
        
        return False
    
    def get_statistics(self) -> Dict:
        """Статистика работы системы безопасности"""
        return {
            "total_validations": self.total_validations,
            "blocked_actions": self.blocked_actions,
            "confirmed_actions": self.confirmed_actions,
            "block_rate": self.blocked_actions / self.total_validations if self.total_validations > 0 else 0.0
        }
    
    def update_policy(self, key: str, value: Any):
        """Обновление политики безопасности"""
        self.policies[key] = value
        logger.info(f"✅ Обновлена политика: {key} = {value}")
