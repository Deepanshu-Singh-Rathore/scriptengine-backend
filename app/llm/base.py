"""
Base LLM client abstraction.
"""
from abc import ABC, abstractmethod
from typing import List


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    async def generate_code(self, prompt: str) -> str:
        """Generate code from prompt."""
        pass
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        pass
