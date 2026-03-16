"""Tests for class reordering in OrderedMdxCodeDocumentation."""

from __future__ import annotations

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority

from .conftest import FILE_KEY, MOCK_CONTEXT, MODULES, build_ordered_doc, class_order


class TestReorderClasses:
    def test_single_priority_class_moves_to_top(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClient"])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = class_order(result)
        assert order[0] == "InfrahubClient"

    def test_multiple_priority_classes_in_specified_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClientSync", "InfrahubClient"])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = class_order(result)
        assert order[0] == "InfrahubClientSync"
        assert order[1] == "InfrahubClient"

    def test_non_priority_classes_retain_original_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClient"])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = class_order(result)
        remaining = order[1:]
        assert remaining == ["ProcessRelationsNode", "BaseClient", "InfrahubClientSync"]

    def test_no_priority_config_returns_unchanged(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority()
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == sample_mdx

    def test_empty_classes_list_returns_unchanged(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=[])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == sample_mdx

    def test_nonexistent_class_name_raises(self, sample_mdx: str) -> None:
        # Arrange
        fake_class_name = "DoesNotExist"
        priority = PagePriority(classes=[fake_class_name])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match=fake_class_name):
            doc.generate(MOCK_CONTEXT, MODULES)

    def test_reorder_page_without_methods(self, sample_mdx_no_methods: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubNodeMode"])
        doc = build_ordered_doc(sample_mdx_no_methods, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = class_order(result)
        assert order == ["InfrahubNodeMode", "RelatedNodeState"]
