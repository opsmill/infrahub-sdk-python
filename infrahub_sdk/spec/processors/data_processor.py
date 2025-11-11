from abc import ABC, abstractmethod
from typing import Any


class DataProcessor(ABC):
    """Abstract base class for data processing strategies"""

    @abstractmethod
    async def process_data(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process the data according to the strategy"""
