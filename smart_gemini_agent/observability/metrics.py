"""
Система метрик для агента
Отслеживание производительности и качества
"""

import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class TaskMetrics:
    """Метрики выполнения задачи"""
    task_id: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    tools_used: List[str] = field(default_factory=list)
    error_type: Optional[str] = None
    quality_score: Optional[float] = None
    
    @property
    def duration(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return None


class AgentMetrics:
    """
    Система метрик для отслеживания производительности агента
    
    Основные метрики согласно agents.md:
    - Коэффициент достижения целей
    - Латентность выполнения
    - Количество вызовов инструментов
    - Стоимость на взаимодействие
    - Коэффициент восстановления после ошибок
    """
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        
        # История задач
        self.task_history: deque = deque(maxlen=max_history)
        
        # Счетчики
        self.total_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.recovered_tasks = 0  # Задачи, восстановленные после ошибки
        
        # Статистика по инструментам
        self.tool_usage: Dict[str, int] = defaultdict(int)
        self.tool_errors: Dict[str, int] = defaultdict(int)
        self.tool_durations: Dict[str, List[float]] = defaultdict(list)
        
        # Статистика по ошибкам
        self.error_counts: Dict[str, int] = defaultdict(int)
        
        # Качество
        self.quality_scores: List[float] = []
        
        logger.info("✅ Инициализирована система метрик агента")
    
    def start_task(self, task_id: str) -> TaskMetrics:
        """Начало отслеживания задачи"""
        metrics = TaskMetrics(
            task_id=task_id,
            start_time=time.time()
        )
        self.total_tasks += 1
        return metrics
    
    def complete_task(
        self, 
        metrics: TaskMetrics, 
        success: bool,
        error_type: Optional[str] = None,
        quality_score: Optional[float] = None
    ):
        """Завершение отслеживания задачи"""
        metrics.end_time = time.time()
        metrics.success = success
        metrics.error_type = error_type
        metrics.quality_score = quality_score
        
        # Обновляем счетчики
        if success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1
            if error_type:
                self.error_counts[error_type] += 1
        
        # Сохраняем качество
        if quality_score is not None:
            self.quality_scores.append(quality_score)
        
        # Добавляем в историю
        self.task_history.append(metrics)
        
        logger.info(
            f"📊 Задача {metrics.task_id}: "
            f"{'✅ успех' if success else '❌ ошибка'}, "
            f"время: {metrics.duration:.2f}с"
        )
    
    def record_tool_call(self, tool_name: str, duration: float, success: bool):
        """Запись вызова инструмента"""
        self.tool_usage[tool_name] += 1
        self.tool_durations[tool_name].append(duration)
        
        if not success:
            self.tool_errors[tool_name] += 1
    
    def record_recovery(self):
        """Запись успешного восстановления после ошибки"""
        self.recovered_tasks += 1
    
    def get_success_rate(self) -> float:
        """Коэффициент успешности"""
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks
    
    def get_recovery_rate(self) -> float:
        """Коэффициент восстановления после ошибок"""
        if self.failed_tasks == 0:
            return 0.0
        return self.recovered_tasks / (self.failed_tasks + self.recovered_tasks)
    
    def get_average_duration(self) -> float:
        """Средняя длительность выполнения задачи"""
        durations = [
            m.duration for m in self.task_history 
            if m.duration is not None
        ]
        return sum(durations) / len(durations) if durations else 0.0
    
    def get_average_quality(self) -> float:
        """Средняя оценка качества"""
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores) / len(self.quality_scores)
    
    def get_tool_statistics(self) -> Dict[str, Dict]:
        """Статистика по использованию инструментов"""
        stats = {}
        
        for tool_name, count in self.tool_usage.items():
            durations = self.tool_durations.get(tool_name, [])
            errors = self.tool_errors.get(tool_name, 0)
            
            stats[tool_name] = {
                "usage_count": count,
                "error_count": errors,
                "error_rate": errors / count if count > 0 else 0.0,
                "avg_duration": sum(durations) / len(durations) if durations else 0.0,
                "total_duration": sum(durations)
            }
        
        return stats
    
    def get_summary(self) -> Dict:
        """Полная сводка метрик"""
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": self.get_success_rate(),
            "recovery_rate": self.get_recovery_rate(),
            "average_duration": self.get_average_duration(),
            "average_quality": self.get_average_quality(),
            "tool_statistics": self.get_tool_statistics(),
            "error_distribution": dict(self.error_counts)
        }
    
    def export_metrics(self) -> Dict:
        """Экспорт всех метрик в формате для мониторинга"""
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": self.get_summary(),
            "recent_tasks": [
                {
                    "task_id": m.task_id,
                    "duration": m.duration,
                    "success": m.success,
                    "tools_used": m.tools_used,
                    "quality_score": m.quality_score
                }
                for m in list(self.task_history)[-10:]  # Последние 10
            ]
        }
    
    def print_summary(self):
        """Вывод сводки в консоль"""
        summary = self.get_summary()
        
        print("\n" + "="*60)
        print("📊 МЕТРИКИ АГЕНТА")
        print("="*60)
        print(f"Всего задач: {summary['total_tasks']}")
        print(f"✅ Успешных: {summary['successful_tasks']}")
        print(f"❌ Неудачных: {summary['failed_tasks']}")
        print(f"📈 Коэффициент успеха: {summary['success_rate']:.1%}")
        print(f"🔄 Коэффициент восстановления: {summary['recovery_rate']:.1%}")
        print(f"⏱️  Среднее время: {summary['average_duration']:.2f}с")
        print(f"⭐ Средняя оценка качества: {summary['average_quality']:.2f}/10")
        
        print("\n🔧 ТОП-5 используемых инструментов:")
        tool_stats = summary['tool_statistics']
        sorted_tools = sorted(
            tool_stats.items(), 
            key=lambda x: x[1]['usage_count'], 
            reverse=True
        )[:5]
        
        for tool_name, stats in sorted_tools:
            print(f"  • {tool_name}: {stats['usage_count']} вызовов "
                  f"(ошибок: {stats['error_rate']:.1%})")
        
        if summary['error_distribution']:
            print("\n⚠️  Распределение ошибок:")
            for error_type, count in summary['error_distribution'].items():
                print(f"  • {error_type}: {count}")
        
        print("="*60 + "\n")
