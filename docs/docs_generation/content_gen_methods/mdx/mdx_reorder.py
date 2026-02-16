from __future__ import annotations

from .mdx_ordered_section import OrderedMdxSection
from .mdx_priority import PagePriority, SectionPriority
from .mdx_section import ASection, _parse_sections


def reorder_mdx_content(content: str, priority: PagePriority) -> str:
    """Reorder classes and methods on an MDX page according to *priority*.

    Parses the MDX into H2 sections (``## Functions``, ``## Classes``),
    then wraps each in an :class:`OrderedMdxSection` that reorders H3
    class sections by ``priority.classes`` and, for each class with
    entries in ``priority.methods``, reorders H4 method sections too.

    If *priority* has no configuration, the content is returned as-is.
    """
    if not priority.classes and not priority.methods:
        return content

    lines = content.split("\n")
    preamble, h2_sections = _parse_sections(lines, heading_level=2)

    section_priority = SectionPriority(names=priority.classes, sub_priorities=priority.methods)
    reordered: list[ASection] = [
        OrderedMdxSection(section=h2, priority=section_priority, child_heading_level=3) for h2 in h2_sections
    ]

    result = list(preamble)
    for section in reordered:
        result.extend(section.lines)
    return "\n".join(result)
