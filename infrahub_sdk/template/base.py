from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ATemplate(ABC):
    """Abstract base class defining the minimal template rendering contract."""

    @abstractmethod
    async def render(self, variables: dict[str, Any]) -> str: ...
