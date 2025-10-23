"""
Smart Gemini Agent - Модульная версия
Умный AI-агент для работы с файловой системой на базе Google Gemini
"""

from .config.agent_config import AgentConfig
from .core.agent import FileSystemAgent
from .ui.rich_chat import RichInteractiveChat

__version__ = "2.0.0"
__author__ = "Smart Gemini Agent Team"

__all__ = ["AgentConfig", "FileSystemAgent", "RichInteractiveChat"]
