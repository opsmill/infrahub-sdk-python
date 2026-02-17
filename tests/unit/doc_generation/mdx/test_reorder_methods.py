"""Tests for method reordering in OrderedMdxCodeDocumentation."""

from __future__ import annotations

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority

from .conftest import FILE_KEY, MOCK_CONTEXT, MODULES, build_ordered_doc, class_order, method_order


class TestReorderMethods:
    def test_single_priority_method_moves_to_top(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert method_order(result, "InfrahubClient")[0] == "save"

    def test_multiple_priority_methods_in_specified_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["delete", "save"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = method_order(result, "InfrahubClient")
        assert order[0] == "delete"
        assert order[1] == "save"

    def test_non_priority_methods_retain_original_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = method_order(result, "InfrahubClient")
        assert order[0] == "save"
        assert order[1:] == ["get_version", "create", "get", "get", "delete"]

    def test_method_only_priority_no_class_reordering(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert class_order(result) == ["ProcessRelationsNode", "BaseClient", "InfrahubClient", "InfrahubClientSync"]

    def test_combined_class_and_method_reordering(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(
            classes=["InfrahubClient"],
            methods={"InfrahubClient": ["save"]},
        )
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert class_order(result)[0] == "InfrahubClient"
        assert method_order(result, "InfrahubClient")[0] == "save"

    def test_overloaded_methods_move_together(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["get"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        order = method_order(result, "InfrahubClient")
        assert order[0] == "get"
        assert order[1] == "get"
        assert order[2:] == ["get_version", "create", "save", "delete"]

    def test_nonexistent_method_name_raises(self, sample_mdx: str) -> None:
        # Arrange
        fake_method_name = "nonexistent"
        priority = PagePriority(methods={"InfrahubClient": [fake_method_name, "save"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match=("%s" % fake_method_name)):
            doc.generate(MOCK_CONTEXT, MODULES)

    def test_method_priority_for_nonexistent_class_raises(self, sample_mdx: str) -> None:
        # Arrange
        fake_class_name = "DoesNotExist"
        priority = PagePriority(methods={("%s" % fake_class_name): ["get"]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match=fake_class_name):
            doc.generate(MOCK_CONTEXT, MODULES)
