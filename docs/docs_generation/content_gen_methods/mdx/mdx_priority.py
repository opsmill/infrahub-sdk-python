from __future__ import annotations

from dataclasses import dataclass, field


def _duplicates(items: list[str]) -> list[str]:
    """Return items that appear more than once, in order of first extra occurrence."""
    seen: set[str] = set()
    dupes: list[str] = []
    for item in items:
        if item in seen and item not in dupes:
            dupes.append(item)
        seen.add(item)
    return dupes


@dataclass(frozen=True)
class PagePriority:
    """Priority ordering configuration for a single documentation page.

    Attributes:
        sections: Ordered list of H2 section names to appear first (e.g. ``"Classes"``).
        classes: Ordered list of class/function names to appear first on the page.
        methods: Per-class ordered list of method names to appear first.
            Key is class name, value is ordered method name list.

    """

    sections: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    methods: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors = [f"Duplicate section '{s}'" for s in _duplicates(self.sections)]
        errors.extend(f"Duplicate class '{c}'" for c in _duplicates(self.classes))
        for cls_name, methods in self.methods.items():
            errors.extend(f"Duplicate method '{m}' for class '{cls_name}'" for m in _duplicates(methods))
        if errors:
            raise ValueError("Invalid priority configuration:\n" + "\n".join(f"  - {e}" for e in errors))


@dataclass(frozen=True)
class SectionPriority:
    """Priority configuration for reordering child sections.

    Attributes:
        names: Ordered list of child section names to appear first.
        sub_priorities: Per-child priorities for deeper nesting.
            Key is child name, value is ordered subsection name list.

    """

    names: list[str] = field(default_factory=list)
    sub_priorities: dict[str, list[str]] = field(default_factory=dict)
