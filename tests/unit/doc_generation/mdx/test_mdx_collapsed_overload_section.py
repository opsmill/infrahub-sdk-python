"""Tests for CollapsedOverloadSection."""

from __future__ import annotations

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_collapsed_overload_section import (
    CollapsedOverloadSection,
)
from docs.docs_generation.content_gen_methods.mdx.mdx_section import ASection

from .conftest import make_method_section


class TestCollapsedOverloadSection:
    def test_heading_delegates_to_primary(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str)")
        section = CollapsedOverloadSection(primary=primary, others=[])

        # Act
        result = section.heading

        # Assert
        assert result == primary.heading

    def test_no_others_returns_primary_content_only(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str)")
        section = CollapsedOverloadSection(primary=primary, others=[])

        # Act
        result = section.content

        # Assert
        assert result == primary.content
        assert "<details>" not in "\n".join(result)

    def test_others_rendered_in_details_block(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str, id: int)")
        other1 = make_method_section("get", "get(self, kind: str)")
        other2 = make_method_section("get", "get(self)")
        section = CollapsedOverloadSection(primary=primary, others=[other1, other2])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<details>" in result
        assert "<summary>Show 2 other overloads</summary>" in result
        assert "</details>" in result

    def test_singular_label_for_one_other(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str)")
        other = make_method_section("get", "get(self)")
        section = CollapsedOverloadSection(primary=primary, others=[other])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<summary>Show 1 other overload</summary>" in result

    def test_plural_label_for_multiple_others(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, a: int, b: int, c: int)")
        others = [make_method_section("get", f"get(self, x{i}: int)") for i in range(3)]
        section = CollapsedOverloadSection(primary=primary, others=others)

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<summary>Show 3 other overloads</summary>" in result

    def test_lines_includes_heading_plus_content(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str)")
        section = CollapsedOverloadSection(primary=primary, others=[])

        # Act
        result = section.lines

        # Assert
        assert result[0] == section.heading
        assert result[1:] == section.content

    def test_is_asection_subclass(self) -> None:
        # Assert
        assert issubclass(CollapsedOverloadSection, ASection)

    def test_details_block_contains_other_section_lines(self) -> None:
        # Arrange
        primary = make_method_section("get", "get(self, kind: str, id: int)")
        other = make_method_section("get", "get(self, kind: str)", docstring="Get by kind.")
        section = CollapsedOverloadSection(primary=primary, others=[other])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "Get by kind." in result
        assert "get(self, kind: str)" in result


class TestCollapsedOverloadSectionFromOverloads:
    def test_primary_is_overload_with_most_params(self) -> None:
        # Arrange
        s1 = make_method_section("get", "get(self, a: int, b: int)")
        s2 = make_method_section("get", "get(self, a: int, b: int, c: int, d: int, e: int)")
        s3 = make_method_section("get", "get(self, a: int, b: int, c: int)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1, s2, s3])

        # Assert
        assert "e: int" in "\n".join(section.primary.lines)
        assert len(section.others) == 2

    def test_tie_breaking_selects_first_in_source_order(self) -> None:
        # Arrange
        s1 = make_method_section("get", "get(self, a: int, b: str)")
        s2 = make_method_section("get", "get(self, x: int, y: str)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1, s2])

        # Assert
        assert "a: int" in "\n".join(section.primary.lines)
        assert len(section.others) == 1

    def test_single_section_returns_no_others(self) -> None:
        # Arrange
        s1 = make_method_section("get", "get(self, kind: str)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1])

        # Assert
        assert section.primary is s1
        assert section.others == []

    def test_empty_list_raises(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            CollapsedOverloadSection.from_overloads([])
