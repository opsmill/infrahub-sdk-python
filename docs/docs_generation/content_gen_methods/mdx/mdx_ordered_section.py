from __future__ import annotations

from dataclasses import dataclass

from .mdx_priority import SectionPriority
from .mdx_section import ASection, MdxSection, _parse_sections


@dataclass
class OrderedMdxSection(ASection):
    """Decorator around MdxSection that reorders child sections by priority.

    Reorders immediate children at ``child_heading_level`` according to
    ``priority.names``.  Children whose name appears in
    ``priority.sub_priorities`` are themselves wrapped in a nested
    :class:`OrderedMdxSection` that reorders *their* children one
    heading level deeper.
    """

    section: MdxSection
    priority: SectionPriority
    child_heading_level: int

    @property
    def heading(self) -> str:
        return self.section.heading

    @property
    def content(self) -> list[str]:
        if not self.priority.names and not self.priority.sub_priorities:
            return self.section.content
        parsed = _parse_sections(self.section.content, heading_level=self.child_heading_level)
        if not parsed.sections:
            return self.section.content
        parsed = parsed.reordered(self.priority.names)
        children = self._apply_sub_priorities(parsed.sections)
        return parsed.reassembled(children)

    def _apply_sub_priorities(self, sections: list[MdxSection]) -> list[ASection]:
        """Wrap children that have sub-priorities in nested :class:`OrderedMdxSection`."""
        if not self.priority.sub_priorities:
            return list(sections)
        result: list[ASection] = []
        for section in sections:
            if section.name in self.priority.sub_priorities:
                result.append(
                    OrderedMdxSection(
                        section=section,
                        priority=SectionPriority(names=self.priority.sub_priorities[section.name]),
                        child_heading_level=self.child_heading_level + 1,
                    )
                )
            else:
                result.append(section)
        return result
