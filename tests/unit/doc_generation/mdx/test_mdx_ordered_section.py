"""Tests for OrderedMdxSection."""

from __future__ import annotations

import re

from docs.docs_generation.content_gen_methods.mdx.mdx_ordered_section import OrderedMdxSection
from docs.docs_generation.content_gen_methods.mdx.mdx_priority import SectionPriority
from docs.docs_generation.content_gen_methods.mdx.mdx_section import ASection, MdxSection


class TestOrderedMdxSection:
    def test_content_returns_reordered_children(self) -> None:
        # Arrange
        children = [
            "### `Alpha`\n",
            "Alpha body\n",
            "### `Bravo`\n",
            "Bravo body\n",
            "### `Charlie`\n",
            "Charlie body",
        ]
        ordered = _make_ordered("Classes", 2, children, priority=SectionPriority(names=["Charlie", "Alpha"]))

        # Act
        content = ordered.content

        # Assert
        content_str = "\n".join(content)
        names = re.findall(r"^### `([^`]+)`", content_str, re.MULTILINE)
        assert names == ["Charlie", "Alpha", "Bravo"]

    def test_lines_includes_heading_plus_ordered_content(self) -> None:
        # Arrange
        children = [
            "### `A`\n",
            "### `B`\n",
        ]
        ordered = _make_ordered("Classes", 2, children, priority=SectionPriority(names=["B"]))

        # Act
        lines = ordered.lines

        # Assert
        assert lines[0] == "## `Classes`"
        names = re.findall(r"^### `([^`]+)`", "\n".join(lines), re.MULTILINE)
        assert names == ["B", "A"]

    def test_empty_priority_returns_original_content(self) -> None:
        # Arrange
        ordered = _make_ordered("Sec", 2, ["### `X`\n", "body"], priority=SectionPriority())
        base = MdxSection(name="Sec", heading_level=2, _lines=["## `Sec`", "### `X`\n", "body"])

        # Act
        content = ordered.content

        # Assert
        assert content == base.content

    def test_no_children_returns_original_content(self) -> None:
        # Arrange
        ordered = _make_ordered("Sec", 2, ["Just some text"], priority=SectionPriority(names=["Anything"]))
        base = MdxSection(name="Sec", heading_level=2, _lines=["## `Sec`", "Just some text"])

        # Act
        content = ordered.content

        # Assert
        assert content == base.content

    def test_is_asection_subclass(self) -> None:
        # Arrange
        section = MdxSection(name="MySection", heading_level=2, _lines=["## `MySection`"])
        ordered = OrderedMdxSection(section=section, priority=SectionPriority(), child_heading_level=3)

        # Assert
        assert isinstance(ordered, ASection)
        assert isinstance(section, ASection)
        assert ordered.heading == "## `MySection`"


def _make_ordered(
    name: str,
    heading_level: int,
    children_lines: list[str],
    priority: SectionPriority,
    child_heading_level: int = 3,
) -> OrderedMdxSection:
    heading = "#" * heading_level + f" `{name}`"
    section = MdxSection(name=name, heading_level=heading_level, _lines=[heading] + children_lines)
    return OrderedMdxSection(
        section=section,
        priority=priority,
        child_heading_level=child_heading_level,
    )
