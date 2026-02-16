from __future__ import annotations

from dataclasses import dataclass

from .mdx_priority import SectionPriority
from .mdx_section import ASection, MdxSection, _parse_sections, _reassemble


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
        inner_preamble, child_sections = _parse_sections(self.section.content, heading_level=self.child_heading_level)
        if not child_sections:
            return self.section.content
        reordered = self._apply_priority_order(child_sections)
        children = self._apply_sub_priorities(reordered)
        return _reassemble(inner_preamble, children)

    def _apply_priority_order(self, sections: list[MdxSection]) -> list[MdxSection]:
        """Reorder *sections* so those matching priority names come first.

        Priority sections appear in the order given by ``self.priority.names``.
        Non-priority sections retain their original relative order.
        Names not found in *sections* are silently skipped (validation is separate).
        """
        by_name: dict[str, list[MdxSection]] = {}
        for section in sections:
            by_name.setdefault(section.name, []).append(section)

        ordered: list[MdxSection] = []
        used_names: set[str] = set()

        for name in self.priority.names:
            if name in by_name and name not in used_names:
                ordered.extend(by_name[name])
                used_names.add(name)

        ordered.extend(section for section in sections if section.name not in used_names)

        return ordered

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
