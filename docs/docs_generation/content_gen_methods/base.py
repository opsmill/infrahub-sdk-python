from __future__ import annotations

from abc import ABC, abstractmethod


class ADocContentGenMethod(ABC):
    """Strategy for producing documentation content as a string.

    Each subclass implements ``apply()`` for a specific content source
    (Jinja2 template, CLI command, pre-generated file, ...).
    """

    @abstractmethod
    def apply(self) -> str:
        """Generate the documentation content."""
