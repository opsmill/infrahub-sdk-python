from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING

from .mdx_code_doc import ACodeDocumentation, MdxFile
from .mdx_collapsed_overload_section import CollapsedOverloadSection, MethodSignature
from .mdx_section import ASection, MdxSection, _parse_sections

if TYPE_CHECKING:
    from invoke import Context


@dataclass
class CollapsedOverloadCodeDocumentation(ACodeDocumentation):
    """Decorator around :class:`ACodeDocumentation` that collapses overloaded methods.

    Delegates generation to the wrapped *documentation* instance, then
    replaces groups of same-name H4 method sections within each class
    with a :class:`CollapsedOverloadSection` showing the primary overload
    and a collapsible ``<details>`` block for the rest.
    """

    documentation: ACodeDocumentation

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        """Generate MDX files and collapse overloaded methods in each one."""
        files = self.documentation.generate(context, modules_to_document)
        return {name: self._collapse_overloads(mdx_file) for name, mdx_file in files.items()}

    def _collapse_overloads(self, mdx_file: MdxFile) -> MdxFile:
        """Return a copy of *mdx_file* with overloaded methods collapsed."""
        lines = mdx_file.content.split("\n")
        parsed_h2 = _parse_sections(lines, heading_level=2)

        processed_h2: list[ASection] = []
        for h2 in parsed_h2.sections:
            processed_h3 = self._process_class_sections(h2.content)
            if processed_h3 is None:
                # No subsection means no method to manage
                processed_h2.append(h2)
            else:
                h3_parsed = _parse_sections(h2.content, heading_level=3)
                new_lines = h3_parsed.reassembled(processed_h3)
                processed_h2.append(
                    MdxSection(name=h2.name, heading_level=h2.heading_level, _lines=[h2.heading] + new_lines)
                )

        new_content = "\n".join(parsed_h2.reassembled(processed_h2))
        return MdxFile(name=mdx_file.name, content=new_content, source_path=mdx_file.source_path)

    def _process_class_sections(self, h2_content: list[str]) -> list[ASection] | None:
        """Collapse overloads inside each H3 class section, or return ``None`` if nothing changed."""
        h3_parsed = _parse_sections(h2_content, heading_level=3)
        if not h3_parsed.sections:
            return None

        any_collapsed = False
        processed: list[ASection] = []
        for h3 in h3_parsed.sections:
            collapsed_methods = self._collapse_methods_in_class(h3.content)
            if collapsed_methods is None:
                processed.append(h3)
            else:
                any_collapsed = True
                h4_parsed = _parse_sections(h3.content, heading_level=4)
                new_lines = h4_parsed.reassembled(collapsed_methods)
                processed.append(
                    MdxSection(name=h3.name, heading_level=h3.heading_level, _lines=[h3.heading] + new_lines)
                )

        return processed if any_collapsed else None

    def _collapse_methods_in_class(self, h3_content: list[str]) -> list[ASection] | None:
        """Collapse consecutive same-name H4 methods, or return ``None`` if no overloads found."""
        h4_parsed = _parse_sections(h3_content, heading_level=4)
        if not h4_parsed.sections:
            return None

        groups = self._group_consecutive_overloads(h4_parsed.sections)
        has_overloads = any(len(group) > 1 for group in groups)
        if not has_overloads:
            return None

        collapsed: list[ASection] = []
        for group in groups:
            if len(group) == 1:
                collapsed.append(group[0])
            else:
                accessors, overloads = _split_property_accessors(group)
                collapsed.extend(accessors)
                if len(overloads) > 1:
                    collapsed.append(CollapsedOverloadSection.from_overloads(overloads))
                else:
                    collapsed.extend(overloads)
        return collapsed

    @staticmethod
    def _group_consecutive_overloads(sections: list[MdxSection]) -> list[list[MdxSection]]:
        """Group consecutive sections sharing the same name."""
        return [list(group) for _, group in groupby(sections, key=lambda s: s.name)]


def _split_property_accessors(sections: list[MdxSection]) -> tuple[list[MdxSection], list[MdxSection]]:
    """Partition *sections* into property accessors and remaining overloads.

    Recognised accessor patterns:

    * **getter** — 0 params, non-``None`` return
    * **setter** — 1 param, ``None`` return
    * **deleter** — 0 params, ``None`` return
    """
    sigs = [(section, MethodSignature(section)) for section in sections]

    def is_accessor(sig: MethodSignature) -> bool:
        return getter_sig(sig) or setter_sig(sig) or deleter_sig(sig)

    accessors = [section for section, sig in sigs if is_accessor(sig)]
    overloads = [section for section, sig in sigs if not is_accessor(sig)]
    return accessors, overloads


def deleter_sig(sig: MethodSignature) -> bool:
    return sig.param_count() == 0 and sig.return_type() == "None"


def setter_sig(sig: MethodSignature) -> bool:
    return sig.param_count() == 1 and sig.return_type() == "None"


def getter_sig(sig: MethodSignature) -> bool:
    return sig.param_count() == 0 and sig.return_type() != "None"
