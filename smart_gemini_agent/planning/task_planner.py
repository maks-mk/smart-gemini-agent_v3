"""
Система планирования и декомпозиции задач
"""

import logging
import json
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Приоритет задачи"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(Enum):
    """Статус задачи"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Заблокирована зависимостями


@dataclass
class Subtask:
    """Подзадача в плане выполнения"""
    id: str
    description: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # IDs других подзадач
    estimated_time: Optional[float] = None
    actual_time: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "estimated_time": self.estimated_time,
            "actual_time": self.actual_time,
            "result": self.result,
            "error": self.error
        }


@dataclass
class ExecutionPlan:
    """План выполнения задачи"""
    task_id: str
    main_goal: str
    subtasks: List[Subtask]
    current_step: int = 0
    
    def get_next_task(self) -> Optional[Subtask]:
        """
        Возвращает следующую готовую к выполнению задачу
        Учитывает зависимости и приоритеты
        """
        # Освежаем статусы задач: PENDING/BLOCKED в зависимости от зависимостей
        for t in self.subtasks:
            if t.status in (TaskStatus.PENDING, TaskStatus.BLOCKED):
                if self._are_dependencies_completed(t):
                    t.status = TaskStatus.PENDING
                else:
                    t.status = TaskStatus.BLOCKED

        # Фильтруем только PENDING задачи
        pending_tasks = [t for t in self.subtasks if t.status == TaskStatus.PENDING]

        if not pending_tasks:
            return None

        # Выбираем готовые задачи из PENDING
        ready_tasks = [t for t in pending_tasks if self._are_dependencies_completed(t)]
        if not ready_tasks:
            return None
        
        # Сортируем по приоритету
        priority_order = {
            TaskPriority.HIGH: 0,
            TaskPriority.MEDIUM: 1,
            TaskPriority.LOW: 2
        }
        ready_tasks.sort(key=lambda t: priority_order[t.priority])
        
        return ready_tasks[0]
    
    def _are_dependencies_completed(self, task: Subtask) -> bool:
        """Проверка завершения всех зависимостей"""
        if not task.dependencies:
            return True
        
        for dep_id in task.dependencies:
            dep_task = self._find_task_by_id(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        
        return True
    
    def _find_task_by_id(self, task_id: str) -> Optional[Subtask]:
        """Поиск подзадачи по ID"""
        for task in self.subtasks:
            if task.id == task_id:
                return task
        return None
    
    def get_progress(self) -> Dict:
        """Прогресс выполнения плана"""
        total = len(self.subtasks)
        completed = sum(1 for t in self.subtasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.subtasks if t.status == TaskStatus.FAILED)
        in_progress = sum(1 for t in self.subtasks if t.status == TaskStatus.IN_PROGRESS)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": total - completed - failed - in_progress,
            "completion_rate": completed / total if total > 0 else 0.0
        }
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь"""
        return {
            "task_id": self.task_id,
            "main_goal": self.main_goal,
            "subtasks": [task.to_dict() for task in self.subtasks],
            "current_step": self.current_step,
            "progress": self.get_progress()
        }


class TaskPlanner:
    """
    Система планирования и декомпозиции задач
    
    Согласно agents.md:
    "Это не единичная мысль, а часто цепочка рассуждений"
    """
    
    def __init__(self, llm=None):
        self.llm = llm
        logger.info("✅ TaskPlanner инициализирован")
    
    async def decompose_task(
        self,
        task: str,
        context: Optional[str] = None
    ) -> List[Subtask]:
        """
        Разбивает сложную задачу на подзадачи
        
        Args:
            task: Описание задачи
            context: Дополнительный контекст
        """
        if self.llm is None:
            # Базовая декомпозиция без LLM
            return self._simple_decomposition(task)
        
        # Декомпозиция с помощью LLM
        return await self._llm_decomposition(task, context)
    
    def _simple_decomposition(self, task: str) -> List[Subtask]:
        """Простая декомпозиция без LLM"""
        # Создаем одну подзадачу = исходная задача
        return [
            Subtask(
                id=self._generate_task_id(),
                description=task,
                priority=TaskPriority.HIGH,
                estimated_time=None
            )
        ]
    
    async def _llm_decomposition(
        self,
        task: str,
        context: Optional[str]
    ) -> List[Subtask]:
        """Декомпозиция с помощью LLM"""
        
        decomposition_prompt = f"""
Ты - эксперт по планированию задач. Разбей следующую задачу на логические подзадачи.

Задача: {task}

{f'Контекст: {context}' if context else ''}

Для каждой подзадачи определи:
1. Описание (что нужно сделать)
2. Приоритет (high/medium/low)
3. Зависимости от других подзадач (если есть, укажи номер)
4. Примерное время выполнения в минутах

Формат ответа (JSON):
{{
    "subtasks": [
        {{
            "description": "описание подзадачи",
            "priority": "high|medium|low",
            "dependencies": [],
            "estimated_time": <число минут>
        }}
    ]
}}

Создай логичный план из 3-7 подзадач.
"""
        
        try:
            response = await self.llm.ainvoke(decomposition_prompt)
            subtasks = self._parse_decomposition(response)
            if not subtasks:
                return self._simple_decomposition(task)
            logger.info(f"✅ Задача разбита на {len(subtasks)} подзадач")
            return subtasks
        except Exception as e:
            logger.error(f"Ошибка LLM декомпозиции: {e}")
            return self._simple_decomposition(task)
    
    def _parse_decomposition(self, llm_response) -> List[Subtask]:
        try:
            response_text = self._normalize_llm_content(llm_response)
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)
            
            # Создаем подзадачи
            subtasks = []
            task_id_mapping = {}  # Для маппинга номеров на ID
            
            for i, task_data in enumerate(data.get('subtasks', [])):
                task_id = self._generate_task_id()
                task_id_mapping[i] = task_id
                
                priority_str = task_data.get('priority', 'medium')
                priority = TaskPriority(priority_str) if priority_str in ['high', 'medium', 'low'] else TaskPriority.MEDIUM
                
                subtask = Subtask(
                    id=task_id,
                    description=task_data['description'],
                    priority=priority,
                    dependencies=[],  # Заполним позже
                    estimated_time=task_data.get('estimated_time')
                )
                
                subtasks.append(subtask)
            
            # Теперь преобразуем зависимости (ожидаем 1-базовые индексы)
            for i, task_data in enumerate(data.get('subtasks', [])):
                deps_indices = task_data.get('dependencies', [])
                normalized_deps: List[str] = []
                for dep in deps_indices:
                    try:
                        dep_num = int(dep)
                    except Exception:
                        continue
                    j = dep_num - 1  # 1-базовая -> 0-базовая
                    # Игнорируем самоссылки и индексы вне диапазона
                    if j < 0 or j >= len(subtasks) or j == i:
                        continue
                    normalized_deps.append(task_id_mapping.get(j, subtasks[j].id))
                subtasks[i].dependencies = normalized_deps
            
            return subtasks
        
        except Exception as e:
            logger.error(f"Ошибка парсинга декомпозиции: {e}")
            return []

    def _normalize_llm_content(self, content: Any) -> str:
        try:
            if hasattr(content, 'content'):
                content = content.content
            if isinstance(content, list):
                parts = []
                for x in content:
                    if isinstance(x, dict) and 'text' in x:
                        parts.append(str(x['text']))
                    else:
                        parts.append(str(x))
                return "\n".join(parts)
            if isinstance(content, dict) and 'text' in content and isinstance(content['text'], str):
                return content['text']
            return str(content)
        except Exception:
            return str(content)
    
    async def create_execution_plan(
        self,
        main_goal: str,
        subtasks: Optional[List[Subtask]] = None
    ) -> ExecutionPlan:
        """
        Создает план выполнения
        
        Args:
            main_goal: Основная цель
            subtasks: Список подзадач (если None, будет создан)
        """
        if subtasks is None:
            subtasks = await self.decompose_task(main_goal)
        
        # Топологическая сортировка с учетом зависимостей
        sorted_subtasks = self._topological_sort(subtasks)
        
        plan = ExecutionPlan(
            task_id=self._generate_task_id(),
            main_goal=main_goal,
            subtasks=sorted_subtasks
        )
        
        logger.info(
            f"📋 Создан план выполнения: {len(plan.subtasks)} подзадач"
        )
        
        return plan
    
    def _topological_sort(self, subtasks: List[Subtask]) -> List[Subtask]:
        """
        Топологическая сортировка подзадач с учетом зависимостей
        """
        # Упрощенная реализация - просто возвращаем как есть
        # В полной версии нужно реализовать алгоритм топологической сортировки
        try:
            if not subtasks:
                return subtasks

            # Строим быстрый доступ: id -> задача
            id_to_task: Dict[str, Subtask] = {t.id: t for t in subtasks}

            # Строим граф зависимостей: ребро dep -> task
            from collections import defaultdict, deque

            graph: Dict[str, List[str]] = defaultdict(list)
            indegree: Dict[str, int] = {t.id: 0 for t in subtasks}

            for task in subtasks:
                for dep_id in task.dependencies:
                    if dep_id in id_to_task and dep_id != task.id:
                        graph[dep_id].append(task.id)
                        indegree[task.id] += 1

            # Алгоритм Кана
            queue = deque([tid for tid, deg in indegree.items() if deg == 0])
            sorted_ids: List[str] = []

            while queue:
                current = queue.popleft()
                sorted_ids.append(current)
                for neighbor in graph.get(current, []):
                    indegree[neighbor] -= 1
                    if indegree[neighbor] == 0:
                        queue.append(neighbor)

            # Если обнаружен цикл или несогласованность, возвращаем исходный порядок
            if len(sorted_ids) != len(subtasks):
                return subtasks

            # Преобразуем в список Subtask в новом порядке
            id_to_index = {tid: i for i, tid in enumerate(sorted_ids)}
            return sorted(subtasks, key=lambda t: id_to_index.get(t.id, 0))
        except Exception:
            # На всякий случай не ломаем планировщик при ошибке сортировки
            return subtasks
    
    def _generate_task_id(self) -> str:
        """Генерация уникального ID задачи"""
        return f"task_{uuid.uuid4().hex[:8]}"
    
    def print_plan(self, plan: ExecutionPlan):
        """Вывод плана в консоль"""
        print("\n" + "="*60)
        print(f"📋 ПЛАН ВЫПОЛНЕНИЯ: {plan.main_goal}")
        print("="*60)
        
        progress = plan.get_progress()
        print(f"Прогресс: {progress['completed']}/{progress['total']} "
              f"({progress['completion_rate']:.0%})")
        
        print("\nПодзадачи:")
        for i, task in enumerate(plan.subtasks, 1):
            status_icons = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.IN_PROGRESS: "▶️",
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.BLOCKED: "🚫"
            }
            
            icon = status_icons.get(task.status, "❓")
            priority_icons = {
                TaskPriority.HIGH: "🔴",
                TaskPriority.MEDIUM: "🟡",
                TaskPriority.LOW: "🟢"
            }
            priority_icon = priority_icons.get(task.priority, "")
            
            print(f"{i}. {icon} {priority_icon} {task.description}")
            
            if task.dependencies:
                dep_nums = [
                    str(j+1) for j, t in enumerate(plan.subtasks)
                    if t.id in task.dependencies
                ]
                print(f"   └─ Зависит от: {', '.join(dep_nums)}")
            
            if task.estimated_time:
                print(f"   └─ Время: ~{task.estimated_time} мин")
        
        print("="*60 + "\n")
