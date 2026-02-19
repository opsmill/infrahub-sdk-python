from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field


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


@dataclass
class ParsedContent:
    """Result of splitting MDX lines at a heading level.

    Holds the *preamble* (lines before the first heading) and the
    *sections* found at that level.  Provides reordering and reassembly
    as instance methods so these operations stay with the data they act on.
    """

    preamble: list[str]
    sections: list[MdxSection]

    @property
    def lines(self) -> list[str]:
        """Reassemble preamble and sections into a flat line list."""
        return self.reassembled(self.sections)

    def reassembled(self, sections: Sequence[ASection]) -> list[str]:
        """Combine this preamble with *sections* into a flat line list."""
        result = list(self.preamble)
        for section in sections:
            result.extend(section.lines)
        return result

    def reordered(self, names: list[str]) -> ParsedContent:
        """Return a new :class:`ParsedContent` with sections reordered by *names*.

        Priority sections appear in the order given by *names*.
        Non-priority sections retain their original relative order.
        Handles overloaded names (multiple sections sharing a name) by grouping them.
        Names not found in *sections* are silently skipped.
        """
        if not names:
            return self
        by_name: dict[str, list[MdxSection]] = {}
        for section in self.sections:
            by_name.setdefault(section.name, []).append(section)
        ordered: list[MdxSection] = []
        used: set[str] = set()
        for name in names:
            if name in by_name and name not in used:
                ordered.extend(by_name[name])
                used.add(name)
        ordered.extend(s for s in self.sections if s.name not in used)
        return ParsedContent(preamble=self.preamble, sections=ordered)


def _parse_sections(lines: list[str], heading_level: int) -> ParsedContent:
    """Split *lines* into a preamble and sections at *heading_level*.

    Returns a :class:`ParsedContent` where *preamble* contains every line
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

    return ParsedContent(preamble=preamble, sections=sections)
