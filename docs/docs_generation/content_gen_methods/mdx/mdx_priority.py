from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class SectionPriority:
    """Priority configuration for reordering child sections.

    Attributes:
        names: Ordered list of child section names to appear first.
        sub_priorities: Per-child priorities for deeper nesting.
            Key is child name, value is ordered sub-section name list.
    """

    names: list[str] = field(default_factory=list)
    sub_priorities: dict[str, list[str]] = field(default_factory=dict)
