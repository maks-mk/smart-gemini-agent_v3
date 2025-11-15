"""
Долговременная память агента с векторным хранилищем
"""

import logging
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Запись в долговременной памяти"""
    id: str
    timestamp: str
    interaction_type: str
    user_input: str
    agent_response: str
    tools_used: List[str]
    success: bool
    metadata: Dict[str, Any]
    
    def to_text(self) -> str:
        """Конвертация в текст для эмбеддинга"""
        return f"""
Тип: {self.interaction_type}
Время: {self.timestamp}
Запрос: {self.user_input}
Ответ: {self.agent_response}
Инструменты: {', '.join(self.tools_used)}
Успех: {self.success}
"""


class LongTermMemory:
    """
    Долговременная память агента с векторным поиском
    
    Согласно agents.md:
    "Долговременная память обеспечивает постоянство между сессиями.
    С архитектурной точки зрения это почти всегда реализуется как 
    еще один специализированный инструмент — система RAG"
    """
    
    def __init__(
        self,
        persist_directory: str = "./agent_memory",
        embedding_provider: str = "simple",  # simple или openai
        max_results: int = 5
    ):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(exist_ok=True, parents=True)
        
        self.max_results = max_results
        self.embedding_provider = embedding_provider
        
        # Файл для хранения записей (простая реализация без векторной БД)
        self.memory_file = self.persist_directory / "memory.jsonl"
        
        # Кэш в памяти
        self.memory_cache: List[MemoryEntry] = []
        
        # Загружаем существующие записи
        self._load_memory()
        
        # Если нужна векторная БД, инициализируем её
        self.vectorstore = None
        if embedding_provider == "openai":
            self._init_vectorstore()
        
        logger.info(
            f"✅ Инициализирована долговременная память "
            f"(записей: {len(self.memory_cache)}, provider: {embedding_provider})"
        )
    
    def _init_vectorstore(self):
        """Инициализация векторного хранилища (опционально)"""
        try:
            from langchain_community.vectorstores import Chroma
            from langchain_openai import OpenAIEmbeddings
            
            self.embeddings = OpenAIEmbeddings()
            self.vectorstore = Chroma(
                persist_directory=str(self.persist_directory / "chroma"),
                embedding_function=self.embeddings
            )
            
            logger.info("✅ Векторное хранилище Chroma инициализировано")
            
        except ImportError:
            logger.warning(
                "⚠️  chromadb не установлен. "
                "Используется упрощенный поиск без векторных эмбеддингов. "
                "Установите: pip install chromadb langchain-openai"
            )
        except Exception as e:
            logger.error(f"Ошибка инициализации векторного хранилища: {e}")
    
    def _load_memory(self):
        """Загрузка памяти из файла"""
        if not self.memory_file.exists():
            return
        
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        entry = MemoryEntry(**data)
                        self.memory_cache.append(entry)
            
            logger.debug(f"Загружено {len(self.memory_cache)} записей из памяти")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки памяти: {e}")
    
    async def remember(
        self,
        interaction_type: str,
        user_input: str,
        agent_response: str,
        tools_used: List[str],
        success: bool,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Сохранение взаимодействия в долговременную память
        
        Returns:
            ID сохраненной записи
        """
        import uuid
        
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            interaction_type=interaction_type,
            user_input=user_input,
            agent_response=agent_response,
            tools_used=tools_used,
            success=success,
            metadata=metadata or {}
        )
        
        # Сохраняем в кэш
        self.memory_cache.append(entry)
        
        # Сохраняем в файл
        self._save_entry(entry)
        
        # Сохраняем в векторное хранилище
        if self.vectorstore:
            await self._add_to_vectorstore(entry)
        
        logger.debug(f"💾 Сохранено в память: {entry.interaction_type}")
        
        return entry.id
    
    def _save_entry(self, entry: MemoryEntry):
        """Сохранение записи в файл"""
        try:
            with open(self.memory_file, 'a', encoding='utf-8') as f:
                json.dump(asdict(entry), f, ensure_ascii=False)
                f.write('\n')
        except Exception as e:
            logger.error(f"Ошибка сохранения записи: {e}")
    
    async def _add_to_vectorstore(self, entry: MemoryEntry):
        """Добавление записи в векторное хранилище"""
        try:
            text = entry.to_text()
            metadata = {
                "id": entry.id,
                "timestamp": entry.timestamp,
                "type": entry.interaction_type,
                "success": entry.success
            }
            
            self.vectorstore.add_texts(
                texts=[text],
                metadatas=[metadata]
            )
        except Exception as e:
            logger.error(f"Ошибка добавления в векторное хранилище: {e}")
    
    async def recall_similar(
        self,
        query: str,
        k: Optional[int] = None,
        filter_criteria: Optional[Dict] = None
    ) -> List[MemoryEntry]:
        """
        Поиск похожих взаимодействий
        
        Args:
            query: Запрос для поиска
            k: Количество результатов
            filter_criteria: Фильтры (type, success, etc.)
        """
        k = k or self.max_results
        
        # Если есть векторное хранилище, используем его
        if self.vectorstore:
            return await self._vectorstore_search(query, k, filter_criteria)
        
        # Иначе используем простой текстовый поиск
        return self._simple_search(query, k, filter_criteria)
    
    async def _vectorstore_search(
        self,
        query: str,
        k: int,
        filter_criteria: Optional[Dict]
    ) -> List[MemoryEntry]:
        """Поиск через векторное хранилище"""
        try:
            results = self.vectorstore.similarity_search(
                query,
                k=k,
                filter=filter_criteria
            )
            
            # Находим полные записи по ID
            entries = []
            for doc in results:
                entry_id = doc.metadata.get('id')
                entry = self._find_entry_by_id(entry_id)
                if entry:
                    entries.append(entry)
            
            return entries
            
        except Exception as e:
            logger.error(f"Ошибка векторного поиска: {e}")
            return self._simple_search(query, k, filter_criteria)
    
    def _simple_search(
        self,
        query: str,
        k: int,
        filter_criteria: Optional[Dict]
    ) -> List[MemoryEntry]:
        """Простой текстовый поиск без векторов"""
        query_lower = query.lower()
        
        # Фильтрация
        candidates = self.memory_cache
        if filter_criteria:
            candidates = [
                entry for entry in candidates
                if self._matches_filter(entry, filter_criteria)
            ]
        
        # Поиск по вхождению подстроки
        matches = []
        for entry in candidates:
            text = entry.to_text().lower()
            if query_lower in text:
                matches.append(entry)
        
        # Возвращаем последние k результатов
        return matches[-k:] if len(matches) > k else matches
    
    def _matches_filter(self, entry: MemoryEntry, filters: Dict[str, Any]) -> bool:
        """Проверка соответствия записи фильтрам"""
        for key, value in filters.items():
            if key == "type" and entry.interaction_type != value:
                return False
            elif key == "success" and entry.success != value:
                return False
            elif key in entry.metadata and entry.metadata[key] != value:
                return False
        return True
    
    def _find_entry_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Поиск записи по ID"""
        for entry in self.memory_cache:
            if entry.id == entry_id:
                return entry
        return None
    
    async def get_user_preferences(self, user_id: str) -> Dict:
        """
        Извлечение предпочтений пользователя из истории
        
        Анализирует:
        - Часто используемые инструменты
        - Типичные задачи
        - Стиль взаимодействия
        """
        user_entries = [
            entry for entry in self.memory_cache
            if entry.metadata.get('user_id') == user_id
        ]
        
        if not user_entries:
            return {
                "frequent_tools": [],
                "common_tasks": [],
                "interaction_style": "neutral"
            }
        
        # Анализ часто используемых инструментов
        tool_counts = {}
        for entry in user_entries:
            for tool in entry.tools_used:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        frequent_tools = sorted(
            tool_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # Анализ типичных задач (упрощенно)
        task_types = {}
        for entry in user_entries:
            task_type = entry.interaction_type
            task_types[task_type] = task_types.get(task_type, 0) + 1
        
        common_tasks = sorted(
            task_types.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        return {
            "frequent_tools": [tool for tool, _ in frequent_tools],
            "common_tasks": [task for task, _ in common_tasks],
            "interaction_style": self._infer_style(user_entries),
            "total_interactions": len(user_entries),
            "success_rate": sum(1 for e in user_entries if e.success) / len(user_entries)
        }
    
    def _infer_style(self, entries: List[MemoryEntry]) -> str:
        """Определение стиля взаимодействия"""
        # Упрощенная эвристика
        avg_input_length = sum(len(e.user_input) for e in entries) / len(entries)
        
        if avg_input_length < 50:
            return "concise"  # Краткий
        elif avg_input_length > 200:
            return "detailed"  # Подробный
        else:
            return "balanced"  # Сбалансированный
    
    def get_statistics(self) -> Dict:
        """Статистика памяти"""
        if not self.memory_cache:
            return {
                "total_entries": 0,
                "success_rate": 0.0,
                "most_used_tools": [],
                "interaction_types": {}
            }
        
        # Подсчет статистики
        success_count = sum(1 for e in self.memory_cache if e.success)
        
        tool_counts = {}
        for entry in self.memory_cache:
            for tool in entry.tools_used:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        type_counts = {}
        for entry in self.memory_cache:
            t = entry.interaction_type
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            "total_entries": len(self.memory_cache),
            "success_rate": success_count / len(self.memory_cache),
            "most_used_tools": sorted(
                tool_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "interaction_types": type_counts,
            "oldest_entry": self.memory_cache[0].timestamp if self.memory_cache else None,
            "newest_entry": self.memory_cache[-1].timestamp if self.memory_cache else None
        }
    
    def clear(self):
        """Очистка всей памяти"""
        self.memory_cache.clear()
        
        if self.memory_file.exists():
            self.memory_file.unlink()
        
        if self.vectorstore:
            # Очистка векторного хранилища (если возможно)
            try:
                chroma_dir = self.persist_directory / "chroma"
                if chroma_dir.exists():
                    shutil.rmtree(chroma_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Ошибка очистки векторного хранилища: {e}")
        
        logger.info("🗑️  Память очищена")
