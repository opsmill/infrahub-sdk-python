from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ExporterInterface(ABC):
    @abstractmethod
    async def export(
        self, export_directory: Path, namespaces: list[str], branch: str, exclude: list[str] | None = None
    ) -> None: ...
