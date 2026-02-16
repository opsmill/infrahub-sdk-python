from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PagePriority:
    """Priority ordering configuration for a single documentation page.

    Attributes:
        classes: Ordered list of class/function names to appear first on the page.
        methods: Per-class ordered list of method names to appear first.
            Key is class name, value is ordered method name list.
    """

    classes: list[str] = field(default_factory=list)
    methods: dict[str, list[str]] = field(default_factory=dict)


class ASection(ABC):
    """Abstract base for MDX section types."""

    @property
    @abstractmethod
    def heading(self) -> str: ...

    @property
    @abstractmethod
    def content(self) -> list[str]: ...

    @property
    def lines(self) -> list[str]:
        return [self.heading] + self.content


@dataclass
class MdxSection(ASection):
    """A parsed section of MDX content delimited by a heading.

    Attributes:
        name: Item name extracted from the heading (e.g. class or method name).
        heading_level: Markdown heading level (2, 3, or 4).
        _lines: All lines belonging to this section, including the heading.
    """

    name: str
    heading_level: int
    _lines: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return self._lines[0]

    @property
    def content(self) -> list[str]:
        return self._lines[1:]

    @property
    def lines(self) -> list[str]:
        return self._lines


def _heading_level(line: str) -> int | None:
    """Return the heading level (1-6) if *line* is a Markdown heading, else ``None``."""
    match = re.match(r"^(#{1,6})\s", line)
    return len(match.group(1)) if match else None


def _extract_heading_name(line: str) -> str:
    """Extract the bare name from a heading, stripping backtick quoting.

    Handles ``### `ClassName` `` → ``ClassName`` as well as plain headings.
    """
    match = re.match(r"^#{1,6}\s+`([^`]+)`", line)
    if match:
        return match.group(1)
    match = re.match(r"^#{1,6}\s+(.+)", line)
    if match:
        return match.group(1).strip()
    return ""


def _parse_sections(lines: list[str], heading_level: int) -> tuple[list[str], list[MdxSection]]:
    """Split *lines* into a preamble and sections at *heading_level*.

    Returns ``(preamble, sections)`` where *preamble* contains every line
    before the first heading at the target level, and each
    :class:`MdxSection` runs from its heading until the next heading at the
    same level (or the end of the input).
    """
    preamble: list[str] = []
    sections: list[MdxSection] = []
    current_section: MdxSection | None = None

    for line in lines:
        level = _heading_level(line)
        if level == heading_level:
            if current_section is not None:
                # current_section is now complete
                sections.append(current_section)
            name = _extract_heading_name(line)
            current_section = MdxSection(name=name, heading_level=heading_level, _lines=[line])
        elif current_section is not None:
            # If this not the beginning of a new section of the same heading level, this means this line is a part of
            # the current section
            current_section.lines.append(line)
        else:
            # There is no current section, these lines are part of preamble
            preamble.append(line)

    if current_section is not None:
        sections.append(current_section)

    return preamble, sections


def _reassemble(preamble: list[str], sections: Sequence[ASection]) -> list[str]:
    """Combine preamble lines and section lines back into a flat line list."""
    result = list(preamble)
    for section in sections:
        result.extend(section.lines)
    return result


@dataclass
class OrderedMdxSection(ASection):
    """Decorator around MdxSection that reorders child sections by priority."""

    section: MdxSection
    priority_names: list[str]
    child_heading_level: int

    @property
    def heading(self) -> str:
        return self.section.heading

    @property
    def content(self) -> list[str]:
        if not self.priority_names:
            return self.section.content
        inner_preamble, child_sections = _parse_sections(self.section.content, heading_level=self.child_heading_level)
        if not child_sections:
            return self.section.content
        reordered = self._apply_priority_order(child_sections)
        return _reassemble(inner_preamble, reordered)

    def _apply_priority_order(self, sections: list[MdxSection]) -> list[MdxSection]:
        """Reorder *sections* so those matching priority names come first.

        Priority sections appear in the order given by ``self.priority_names``.
        Non-priority sections retain their original relative order.
        Names not found in *sections* are silently skipped (validation is separate).
        """
        by_name: dict[str, list[MdxSection]] = {}
        for section in sections:
            by_name.setdefault(section.name, []).append(section)

        ordered: list[MdxSection] = []
        used_names: set[str] = set()

        for name in self.priority_names:
            if name in by_name and name not in used_names:
                ordered.extend(by_name[name])
                used_names.add(name)

        for section in sections:
            if section.name not in used_names:
                ordered.append(section)
                used_names.add(section.name)

        return ordered


def reorder_mdx_content(content: str, priority: PagePriority) -> str:
    """Reorder classes on an MDX page according to *priority*.

    Parses the MDX into H2 sections (``## Functions``, ``## Classes``),
    then reorders H3 items within each H2 section based on
    ``priority.classes``.  Content within each section is unchanged.

    If *priority* has no classes configured, the content is returned as-is.
    """
    if not priority.classes and not priority.methods:
        return content

    lines = content.split("\n")
    preamble, h2_sections = _parse_sections(lines, heading_level=2)

    reordered: list[ASection] = list(h2_sections)
    if priority.classes:
        reordered = [
            OrderedMdxSection(section=h2, priority_names=priority.classes, child_heading_level=3) for h2 in h2_sections
        ]

    result = list(preamble)
    for section in reordered:
        result.extend(section.lines)
    return "\n".join(result)
