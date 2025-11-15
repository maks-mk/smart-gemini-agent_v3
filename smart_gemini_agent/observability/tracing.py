"""
Система трассировки для агента
Отслеживание траекторий выполнения
"""

import logging
import time
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    """Span трассировки - одна операция"""
    span_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    status: str = "pending"  # pending, success, error
    error: Optional[str] = None
    
    def duration(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь"""
        data = asdict(self)
        data['duration'] = self.duration()
        return data


@dataclass
class Trace:
    """Полная трассировка задачи"""
    trace_id: str
    task: str
    start_time: float
    end_time: Optional[float] = None
    spans: List[TraceSpan] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_span(self, span: TraceSpan):
        """Добавление span"""
        self.spans.append(span)
    
    def duration(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь для сохранения"""
        return {
            "trace_id": self.trace_id,
            "task": self.task,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration(),
            "spans": [span.to_dict() for span in self.spans],
            "metadata": self.metadata,
            "timestamp": datetime.fromtimestamp(self.start_time).isoformat()
        }


class AgentTracer:
    """
    Система трассировки для отладки агента
    
    Согласно agents.md:
    "Трассировка OpenTelemetry — это высокоточная пошаговая запись 
    всего пути выполнения агента (траектории)"
    
    Отслеживает:
    - Запросы к модели
    - Внутренние рассуждения
    - Вызовы инструментов
    - Параметры и результаты
    """
    
    def __init__(self, traces_dir: str = "./traces", max_traces: int = 100):
        self.traces_dir = Path(traces_dir)
        self.traces_dir.mkdir(exist_ok=True, parents=True)
        
        self.max_traces = max_traces
        self.current_trace: Optional[Trace] = None
        self.current_span: Optional[TraceSpan] = None
        self.traces_history: List[Trace] = []
        
        self._span_counter = 0
        self._trace_counter = 0
        
        logger.info(f"✅ Инициализирована система трассировки (dir: {traces_dir})")
    
    def start_trace(self, task: str, metadata: Optional[Dict] = None) -> Trace:
        """Начало новой трассировки"""
        self._trace_counter += 1
        
        trace = Trace(
            trace_id=f"trace_{self._trace_counter}_{int(time.time())}",
            task=task,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        self.current_trace = trace
        
        logger.debug(f"🔍 Начата трассировка {trace.trace_id}")
        return trace
    
    def end_trace(self):
        """Завершение трассировки"""
        if not self.current_trace:
            logger.warning("Нет активной трассировки для завершения")
            return
        
        self.current_trace.end_time = time.time()
        
        # Сохраняем трассировку
        self._save_trace(self.current_trace)
        
        # Добавляем в историю
        self.traces_history.append(self.current_trace)
        if len(self.traces_history) > self.max_traces:
            self.traces_history.pop(0)
        
        logger.info(
            f"✅ Трассировка {self.current_trace.trace_id} завершена "
            f"({self.current_trace.duration():.2f}с, {len(self.current_trace.spans)} spans)"
        )
        
        self.current_trace = None
    
    @contextmanager
    def span(
        self, 
        name: str, 
        attributes: Optional[Dict] = None,
        parent_id: Optional[str] = None
    ):
        """
        Контекстный менеджер для создания span
        
        Использование:
        with tracer.span("llm_call", {"model": "gemini-2.5-flash"}):
            result = await llm.invoke(prompt)
        """
        span = self.start_span(name, attributes, parent_id)
        
        try:
            yield span
            span.status = "success"
        except Exception as e:
            span.status = "error"
            span.error = str(e)
            logger.error(f"❌ Ошибка в span {name}: {e}")
            raise
        finally:
            self.end_span(span)
    
    def start_span(
        self, 
        name: str, 
        attributes: Optional[Dict] = None,
        parent_id: Optional[str] = None
    ) -> TraceSpan:
        """Начало нового span"""
        self._span_counter += 1
        
        span = TraceSpan(
            span_id=f"span_{self._span_counter}",
            parent_id=parent_id or (self.current_span.span_id if self.current_span else None),
            name=name,
            start_time=time.time(),
            attributes=attributes or {}
        )
        
        if self.current_trace:
            self.current_trace.add_span(span)
        
        self.current_span = span
        
        logger.debug(f"  🔸 Span {name} начат")
        return span
    
    def end_span(self, span: TraceSpan):
        """Завершение span"""
        span.end_time = time.time()
        
        logger.debug(f"  🔹 Span {span.name} завершен ({span.duration():.3f}с)")
        
        # Возвращаемся к родительскому span (упрощенная логика)
        self.current_span = None
    
    def add_event(self, event_name: str, attributes: Optional[Dict] = None):
        """Добавление события в текущий span"""
        if not self.current_span:
            logger.warning("Нет активного span для добавления события")
            return
        
        event = {
            "name": event_name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        }
        
        self.current_span.events.append(event)
        logger.debug(f"    📝 Событие: {event_name}")
    
    def set_attribute(self, key: str, value: Any):
        """Установка атрибута текущего span"""
        if not self.current_span:
            logger.warning("Нет активного span для установки атрибута")
            return
        
        self.current_span.attributes[key] = value
    
    def _save_trace(self, trace: Trace):
        """Сохранение трассировки в файл"""
        try:
            trace_file = self.traces_dir / f"{trace.trace_id}.json"
            
            with open(trace_file, 'w', encoding='utf-8') as f:
                json.dump(trace.to_dict(), f, indent=2, ensure_ascii=False)
            
            logger.debug(f"💾 Трассировка сохранена: {trace_file}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения трассировки: {e}")
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Получение трассировки по ID"""
        # Сначала проверяем историю в памяти
        for trace in self.traces_history:
            if trace.trace_id == trace_id:
                return trace
        
        # Затем пытаемся загрузить из файла
        trace_file = self.traces_dir / f"{trace_id}.json"
        if trace_file.exists():
            return self._load_trace(trace_file)
        
        return None
    
    def _load_trace(self, trace_file: Path) -> Optional[Trace]:
        """Загрузка трассировки из файла"""
        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Восстановление объекта Trace (упрощенная версия)
            trace = Trace(
                trace_id=data['trace_id'],
                task=data['task'],
                start_time=data['start_time'],
                end_time=data.get('end_time'),
                metadata=data.get('metadata', {})
            )
            
            # Восстановление spans
            for span_data in data.get('spans', []):
                span = TraceSpan(
                    span_id=span_data['span_id'],
                    parent_id=span_data.get('parent_id'),
                    name=span_data['name'],
                    start_time=span_data['start_time'],
                    end_time=span_data.get('end_time'),
                    attributes=span_data.get('attributes', {}),
                    events=span_data.get('events', []),
                    status=span_data.get('status', 'unknown'),
                    error=span_data.get('error')
                )
                trace.spans.append(span)
            
            return trace
            
        except Exception as e:
            logger.error(f"Ошибка загрузки трассировки из {trace_file}: {e}")
            return None
    
    def print_trace(self, trace_id: str):
        """Вывод трассировки в консоль"""
        trace = self.get_trace(trace_id)
        if not trace:
            print(f"❌ Трассировка {trace_id} не найдена")
            return
        
        print("\n" + "="*80)
        print(f"🔍 ТРАССИРОВКА: {trace.trace_id}")
        print("="*80)
        print(f"Задача: {trace.task}")
        print(f"Длительность: {trace.duration():.2f}с")
        print(f"Количество операций: {len(trace.spans)}")
        print("\n📋 Последовательность операций:")
        
        for i, span in enumerate(trace.spans, 1):
            indent = "  " * (1 if span.parent_id else 0)
            status_icon = {"success": "✅", "error": "❌", "pending": "⏳"}.get(span.status, "❓")
            
            print(f"{indent}{i}. {status_icon} {span.name} ({span.duration():.3f}с)")
            
            if span.attributes:
                for key, value in span.attributes.items():
                    # Ограничиваем длину значений
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    print(f"{indent}   • {key}: {value_str}")
            
            if span.error:
                print(f"{indent}   ⚠️  Ошибка: {span.error}")
        
        print("="*80 + "\n")
    
    def get_recent_traces(self, count: int = 10) -> List[Trace]:
        """Получение последних трассировок"""
        return self.traces_history[-count:]
    
    def export_traces(self, output_file: str):
        """Экспорт всех трассировок в один файл"""
        try:
            traces_data = [trace.to_dict() for trace in self.traces_history]
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(traces_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Экспортировано {len(traces_data)} трассировок в {output_file}")
            
        except Exception as e:
            logger.error(f"Ошибка экспорта трассировок: {e}")
