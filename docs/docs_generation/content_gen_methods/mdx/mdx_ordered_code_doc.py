from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .mdx_code_doc import ACodeDocumentation, MdxFile
from .mdx_ordered_section import OrderedMdxSection
from .mdx_priority import SectionPriority
from .mdx_section import ASection, MdxSection, _parse_sections

if TYPE_CHECKING:
    from invoke import Context

    from .mdx_priority import PagePriority


def _reorder_by_priority(sections: list[MdxSection], names: list[str]) -> list[MdxSection]:
    if not names:
        return sections
    by_name: dict[str, MdxSection] = {s.name: s for s in sections}
    ordered = [by_name[name] for name in names if name in by_name]
    used = set(names)
    ordered.extend(s for s in sections if s.name not in used)
    return ordered


@dataclass
class OrderedMdxCodeDocumentation(ACodeDocumentation):
    """Decorator around :class:`ACodeDocumentation` that reorders sections by priority.

    Delegates generation to the wrapped *documentation* instance, then applies
    :class:`OrderedMdxSection` reordering to pages that have a corresponding
    :class:`PagePriority` entry.
    """

    documentation: ACodeDocumentation
    page_priorities: dict[str, PagePriority]

    def __post_init__(self) -> None:
        errors: list[str] = []
        for file_key, priority in self.page_priorities.items():
            errors.extend(self._find_duplicate_errors(file_key, priority))
        if errors:
            raise ValueError("Invalid priority configuration:\n" + "\n".join(f"  - {e}" for e in errors))

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        files = self.documentation.generate(context, modules_to_document)
        self._validate_references(files)
        return {name: self._apply_priority(name, mdx_file) for name, mdx_file in files.items()}

    @staticmethod
    def _find_duplicate_errors(file_key: str, priority: PagePriority) -> list[str]:
        errors: list[str] = []

        seen_sections: set[str] = set()
        for section in priority.sections:
            if section in seen_sections:
                errors.append(f"Duplicate section '{section}' in priority for '{file_key}'")
            seen_sections.add(section)

        seen_classes: set[str] = set()
        for cls in priority.classes:
            if cls in seen_classes:
                errors.append(f"Duplicate class '{cls}' in priority for '{file_key}'")
            seen_classes.add(cls)

        for cls_name, methods in priority.methods.items():
            seen_methods: set[str] = set()
            for method in methods:
                if method in seen_methods:
                    errors.append(f"Duplicate method '{method}' for class '{cls_name}' in priority for '{file_key}'")
                seen_methods.add(method)

        return errors

    def _validate_references(self, files: dict[str, MdxFile]) -> None:
        errors: list[str] = []
        for file_key, priority in self.page_priorities.items():
            if file_key not in files:
                errors.append(f"Priority references unknown file key '{file_key}'")
                continue
            errors.extend(self._find_reference_errors(file_key, priority, files[file_key]))
        if errors:
            raise ValueError("Invalid priority configuration:\n" + "\n".join(f"  - {e}" for e in errors))

    def _find_reference_errors(self, file_key: str, priority: PagePriority, mdx_file: MdxFile) -> list[str]:
        errors: list[str] = []
        h2_names, h3_names, h3_to_h4_names = self._extract_headings(mdx_file)

        errors.extend(
            f"Priority section '{section}' not found as heading in '{file_key}'"
            for section in priority.sections
            if section not in h2_names
        )

        errors.extend(
            f"Priority class '{cls}' not found as heading in '{file_key}'"
            for cls in priority.classes
            if cls not in h3_names
        )

        for cls_name, methods in priority.methods.items():
            if cls_name not in h3_names:
                errors.append(f"Priority methods reference unknown class '{cls_name}' in '{file_key}'")
                continue
            errors.extend(
                f"Priority method '{method}' not found under class '{cls_name}' in '{file_key}'"
                for method in methods
                if method not in h3_to_h4_names.get(cls_name, set())
            )

        return errors

    @staticmethod
    def _extract_headings(mdx_file: MdxFile) -> tuple[set[str], set[str], dict[str, set[str]]]:
        lines = mdx_file.content.split("\n")
        _, h2_sections = _parse_sections(lines, heading_level=2)

        h2_names: set[str] = {h2.name for h2 in h2_sections}
        h3_names: set[str] = set()
        h3_to_h4_names: dict[str, set[str]] = {}
        for h2 in h2_sections:
            _, h3_sections = _parse_sections(h2.content, heading_level=3)
            for h3 in h3_sections:
                h3_names.add(h3.name)
                _, h4_sections = _parse_sections(h3.content, heading_level=4)
                h3_to_h4_names[h3.name] = {h4.name for h4 in h4_sections}

        return h2_names, h3_names, h3_to_h4_names

    def _apply_priority(self, name: str, mdx_file: MdxFile) -> MdxFile:
        if name not in self.page_priorities:
            return mdx_file

        priority = self.page_priorities[name]
        if not priority.sections and not priority.classes and not priority.methods:
            return mdx_file

        lines = mdx_file.content.split("\n")
        preamble, h2_sections = _parse_sections(lines, heading_level=2)

        h2_sections = _reorder_by_priority(h2_sections, priority.sections)

        section_priority = SectionPriority(names=priority.classes, sub_priorities=priority.methods)
        reordered: list[ASection] = [
            OrderedMdxSection(section=h2, priority=section_priority, child_heading_level=3) for h2 in h2_sections
        ]

        result = list(preamble)
        for section in reordered:
            result.extend(section.lines)

        return MdxFile(name=mdx_file.name, content="\n".join(result), source_path=mdx_file.source_path)
