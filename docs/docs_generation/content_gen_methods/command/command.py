from __future__ import annotations

from abc import ABC, abstractmethod


class ACommand(ABC):
    """Abstract base for building a shell command string."""

    @abstractmethod
    def build(self) -> str:
        """Return the full command string to execute."""
