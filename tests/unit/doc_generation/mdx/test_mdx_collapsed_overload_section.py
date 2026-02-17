"""Tests for CollapsedOverloadSection and SignatureParameterCount."""

from __future__ import annotations

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_collapsed_overload_section import (
    CollapsedOverloadSection,
    SignatureParameterCount,
)
from docs.docs_generation.content_gen_methods.mdx.mdx_section import ASection, MdxSection


class TestSignatureParameterCount:
    def test_simple_signature_returns_correct_count(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, kind: str, id: int)")

        # Act
        result = counter.value()

        # Assert
        assert result == 2

    def test_self_only_returns_zero(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self)")

        # Act
        result = counter.value()

        # Assert
        assert result == 0

    def test_kwargs_counts_as_one(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, **kwargs: Any)")

        # Act
        result = counter.value()

        # Assert
        assert result == 1

    def test_args_and_kwargs_count_separately(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, *args: str, **kwargs: Any)")

        # Act
        result = counter.value()

        # Assert
        assert result == 2

    def test_nested_brackets_not_split(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, kind: dict[str, int], other: list[str])")

        # Act
        result = counter.value()

        # Assert
        assert result == 2

    def test_deeply_nested_generics(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, x: dict[str, list[tuple[int, ...]]])")

        # Act
        result = counter.value()

        # Assert
        assert result == 1

    def test_signature_with_return_type(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, kind: str) -> InfrahubNode")

        # Act
        result = counter.value()

        # Assert
        assert result == 1

    def test_default_values_dont_affect_count(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get(self, kind: str = ..., id: int = None)")

        # Act
        result = counter.value()

        # Assert
        assert result == 2

    def test_real_world_get_signature(self) -> None:
        # Arrange
        signature = (
            "get(self, kind: str | type[SchemaType], raise_when_missing: bool = True, "
            "at: Timestamp | None = None, branch: str | None = None, "
            "timeout: int | None = None, id: str | None = None, "
            "hfid: list[str] | None = None, include: list[str] | None = None, "
            "exclude: list[str] | None = None, populate_store: bool = True, "
            "fragment: bool = False, prefetch_relationships: bool = False, "
            "property: bool = False, include_metadata: bool = False, "
            "**kwargs: Any) -> InfrahubNode | SchemaType | None"
        )
        counter = SignatureParameterCount(signature=signature)

        # Act
        result = counter.value()

        # Assert
        assert result == 15

    def test_empty_signature(self) -> None:
        # Arrange
        counter = SignatureParameterCount(signature="get()")

        # Act
        result = counter.value()

        # Assert
        assert result == 0


class TestCollapsedOverloadSection:
    def test_heading_delegates_to_primary(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, kind: str)")
        section = CollapsedOverloadSection(primary=primary, others=[])

        # Act
        result = section.heading

        # Assert
        assert result == primary.heading

    def test_no_others_returns_primary_content_only(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, kind: str)")
        section = CollapsedOverloadSection(primary=primary, others=[])

        # Act
        result = section.content

        # Assert
        assert result == primary.content
        assert "<details>" not in "\n".join(result)

    def test_others_rendered_in_details_block(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, kind: str, id: int)")
        other1 = _make_method_section("get", "get(self, kind: str)")
        other2 = _make_method_section("get", "get(self)")
        section = CollapsedOverloadSection(primary=primary, others=[other1, other2])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<details>" in result
        assert "<summary>Show 2 other overloads</summary>" in result
        assert "</details>" in result

    def test_singular_label_for_one_other(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, kind: str)")
        other = _make_method_section("get", "get(self)")
        section = CollapsedOverloadSection(primary=primary, others=[other])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<summary>Show 1 other overload</summary>" in result

    def test_plural_label_for_multiple_others(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, a: int, b: int, c: int)")
        others = [_make_method_section("get", f"get(self, x{i}: int)") for i in range(3)]
        section = CollapsedOverloadSection(primary=primary, others=others)

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "<summary>Show 3 other overloads</summary>" in result

    def test_lines_includes_heading_plus_content(self) -> None:
        # Arrange
        primary = _make_method_section("get", "get(self, kind: str)")
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
        primary = _make_method_section("get", "get(self, kind: str, id: int)")
        other = _make_method_section("get", "get(self, kind: str)", docstring="Get by kind.")
        section = CollapsedOverloadSection(primary=primary, others=[other])

        # Act
        result = "\n".join(section.content)

        # Assert
        assert "Get by kind." in result
        assert "get(self, kind: str)" in result


class TestCollapsedOverloadSectionFromOverloads:
    def test_primary_is_overload_with_most_params(self) -> None:
        # Arrange
        s1 = _make_method_section("get", "get(self, a: int, b: int)")
        s2 = _make_method_section("get", "get(self, a: int, b: int, c: int, d: int, e: int)")
        s3 = _make_method_section("get", "get(self, a: int, b: int, c: int)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1, s2, s3])

        # Assert
        assert "e: int" in "\n".join(section.primary.lines)
        assert len(section.others) == 2

    def test_tie_breaking_selects_first_in_source_order(self) -> None:
        # Arrange
        s1 = _make_method_section("get", "get(self, a: int, b: str)")
        s2 = _make_method_section("get", "get(self, x: int, y: str)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1, s2])

        # Assert
        assert "a: int" in "\n".join(section.primary.lines)
        assert len(section.others) == 1

    def test_single_section_returns_no_others(self) -> None:
        # Arrange
        s1 = _make_method_section("get", "get(self, kind: str)")

        # Act
        section = CollapsedOverloadSection.from_overloads([s1])

        # Assert
        assert section.primary is s1
        assert section.others == []

    def test_empty_list_raises(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            CollapsedOverloadSection.from_overloads([])


# --- Helpers ---


def _make_method_section(name: str, signature: str, docstring: str = "") -> MdxSection:
    """Create an MdxSection mimicking a method entry in MDX output."""
    lines = [
        f"#### `{name}`",
        "",
        "```python",
        signature,
        "```",
    ]
    if docstring:
        lines.extend(("", docstring))
    return MdxSection(name=name, heading_level=4, _lines=lines)
