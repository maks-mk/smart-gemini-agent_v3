"""
Хранилище взаимодействий агента
"""

import logging
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Interaction:
    """Одно взаимодействие с агентом"""
    timestamp: str
    user_input: str
    agent_response: str
    tools_used: List[str]
    duration: float
    success: bool
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class InteractionStore:
    """Хранилище всех взаимодействий для анализа"""
    
    def __init__(self, storage_dir: str = "./interactions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True, parents=True)
        
        self.current_session_file = self.storage_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        
        logger.info(f"✅ InteractionStore инициализирован: {self.current_session_file}")
    
    def save_interaction(self, interaction: Interaction):
        """Сохранение взаимодействия"""
        try:
            with open(self.current_session_file, 'a', encoding='utf-8') as f:
                json.dump(interaction.to_dict(), f, ensure_ascii=False)
                f.write('\n')
        except Exception as e:
            logger.error(f"Ошибка сохранения взаимодействия: {e}")
    
    def load_session(self, session_file: str) -> List[Interaction]:
        """Загрузка сессии"""
        interactions = []
        file_path = Path(session_file)
        
        if not file_path.exists():
            return interactions
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        interactions.append(Interaction(**data))
        except Exception as e:
            logger.error(f"Ошибка загрузки сессии: {e}")
        
        return interactions
