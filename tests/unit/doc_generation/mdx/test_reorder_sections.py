"""Tests for section reordering in OrderedMdxCodeDocumentation."""

from __future__ import annotations

from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority

from .conftest import FILE_KEY, MOCK_CONTEXT, MODULES, build_ordered_doc, class_order, method_order, section_order


class TestReorderSections:
    def test_section_priority_moves_classes_before_functions(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(sections=["Classes"])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert section_order(result) == ["Classes", "Functions"]

    def test_combined_section_class_and_method_reordering(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(
            sections=["Classes"],
            classes=["InfrahubClient"],
            methods={"InfrahubClient": ["save"]},
        )
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert section_order(result) == ["Classes", "Functions"]
        assert class_order(result)[0] == "InfrahubClient"
        assert method_order(result, "InfrahubClient")[0] == "save"

    def test_no_section_priority_retains_original_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(sections=[])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == sample_mdx
