from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .mdx_code_doc import ACodeDocumentation, MdxFile
from .mdx_ordered_section import OrderedMdxSection
from .mdx_priority import SectionPriority
from .mdx_section import ASection, _parse_sections

if TYPE_CHECKING:
    from invoke import Context

    from .mdx_priority import PagePriority


@dataclass
class OrderedMdxCodeDocumentation(ACodeDocumentation):
    """Decorator around :class:`ACodeDocumentation` that reorders sections by priority.

    Delegates generation to the wrapped *documentation* instance, then applies
    :class:`OrderedMdxSection` reordering to pages that have a corresponding
    :class:`PagePriority` entry.
    """

    documentation: ACodeDocumentation
    page_priorities: dict[str, PagePriority]

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        files = self.documentation.generate(context, modules_to_document)
        return {name: self._apply_priority(name, mdx_file) for name, mdx_file in files.items()}

    def _apply_priority(self, name: str, mdx_file: MdxFile) -> MdxFile:
        if name not in self.page_priorities:
            return mdx_file

        priority = self.page_priorities[name]
        if not priority.classes and not priority.methods:
            return mdx_file

        lines = mdx_file.content.split("\n")
        preamble, h2_sections = _parse_sections(lines, heading_level=2)

        section_priority = SectionPriority(names=priority.classes, sub_priorities=priority.methods)
        reordered: list[ASection] = [
            OrderedMdxSection(section=h2, priority=section_priority, child_heading_level=3) for h2 in h2_sections
        ]

        result = list(preamble)
        for section in reordered:
            result.extend(section.lines)

        return MdxFile(name=mdx_file.name, content="\n".join(result), source_path=mdx_file.source_path)
