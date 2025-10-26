from abc import ABC, abstractmethod
from typing import Any

from ..models import InfrahubObjectContext


class DataProcessor(ABC):
    """Abstract base class for data processing strategies"""

    @abstractmethod
    async def process_data(self, data: list[dict[str, Any]], context: InfrahubObjectContext) -> list[dict[str, Any]]:
        """Process the data according to the strategy"""
