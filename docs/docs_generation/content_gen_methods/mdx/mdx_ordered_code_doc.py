from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from .mdx_code_doc import ACodeDocumentation, MdxFile
from .mdx_ordered_section import OrderedMdxSection
from .mdx_priority import SectionPriority
from .mdx_section import ASection, MdxSection, _parse_sections

if TYPE_CHECKING:
    from invoke import Context

    from .mdx_priority import PagePriority


@dataclass
class PageHeadings:
    """Heading structure extracted from an :class:`MdxFile`.

    Parses lazily on first access and caches results.
    """

    mdx_file: MdxFile

    @cached_property
    def h2_names(self) -> set[str]:
        return {s.name for s in self._h2_sections}

    @cached_property
    def h3_names(self) -> set[str]:
        names, _ = self._h3_structure
        return names

    @cached_property
    def h3_to_h4_names(self) -> dict[str, set[str]]:
        _, mapping = self._h3_structure
        return mapping

    @cached_property
    def _h2_sections(self) -> list[MdxSection]:
        lines = self.mdx_file.content.split("\n")
        return _parse_sections(lines, heading_level=2).sections

    @cached_property
    def _h3_structure(self) -> tuple[set[str], dict[str, set[str]]]:
        h3_names: set[str] = set()
        h3_to_h4: dict[str, set[str]] = {}
        for h2 in self._h2_sections:
            for h3 in _parse_sections(h2.content, heading_level=3).sections:
                h3_names.add(h3.name)
                h3_to_h4[h3.name] = {h4.name for h4 in _parse_sections(h3.content, heading_level=4).sections}
        return h3_names, h3_to_h4

    def reference_errors(self, file_key: str, priority: PagePriority) -> list[str]:
        """Return error messages for priority references not found in this file's headings."""
        errors: list[str] = []

        errors.extend(
            f"Priority section '{section}' not found as heading in '{file_key}'"
            for section in priority.sections
            if section not in self.h2_names
        )

        errors.extend(
            f"Priority class '{cls}' not found as heading in '{file_key}'"
            for cls in priority.classes
            if cls not in self.h3_names
        )

        for cls_name, methods in priority.methods.items():
            if cls_name not in self.h3_names:
                errors.append(f"Priority methods reference unknown class '{cls_name}' in '{file_key}'")
                continue
            errors.extend(
                f"Priority method '{method}' not found under class '{cls_name}' in '{file_key}'"
                for method in methods
                if method not in self.h3_to_h4_names.get(cls_name, set())
            )

        return errors


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
        self._validate_references(files)
        return {name: self._apply_priority(name, mdx_file) for name, mdx_file in files.items()}

    def _validate_references(self, files: dict[str, MdxFile]) -> None:
        errors: list[str] = []
        for file_key, priority in self.page_priorities.items():
            if file_key not in files:
                errors.append(f"Priority references unknown file key '{file_key}'")
                continue
            errors.extend(PageHeadings(files[file_key]).reference_errors(file_key, priority))
        if errors:
            raise ValueError("Invalid priority configuration:\n" + "\n".join(f"  - {e}" for e in errors))

    def _apply_priority(self, name: str, mdx_file: MdxFile) -> MdxFile:
        if name not in self.page_priorities:
            return mdx_file

        priority = self.page_priorities[name]
        if not priority.sections and not priority.classes and not priority.methods:
            return mdx_file

        lines = mdx_file.content.split("\n")
        parsed = _parse_sections(lines, heading_level=2).reordered(priority.sections)

        section_priority = SectionPriority(names=priority.classes, sub_priorities=priority.methods)
        reordered: list[ASection] = [
            OrderedMdxSection(section=h2, priority=section_priority, child_heading_level=3) for h2 in parsed.sections
        ]

        return MdxFile(
            name=mdx_file.name, content="\n".join(parsed.reassembled(reordered)), source_path=mdx_file.source_path
        )
