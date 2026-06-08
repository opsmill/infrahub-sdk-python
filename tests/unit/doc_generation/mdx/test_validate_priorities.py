"""Tests for priority validation in OrderedMdxCodeDocumentation."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import MdxFile
from docs.docs_generation.content_gen_methods.mdx.mdx_ordered_code_doc import OrderedMdxCodeDocumentation
from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority

from .conftest import FILE_KEY, MOCK_CONTEXT, MODULES, StubDocumentation, build_ordered_doc


class TestNonexistentPriorities:
    def test_nonexistent_file_key_raises(self) -> None:
        # Arrange
        content = "# some content"
        inner = StubDocumentation({"actual.mdx": MdxFile(name="actual.mdx", content=content, source_path=Path("a.py"))})
        fake_file_name = "missing.mdx"
        doc = OrderedMdxCodeDocumentation(
            documentation=inner,
            page_priorities={fake_file_name: PagePriority(classes=["Foo"])},
        )

        # Act / Assert
        with pytest.raises(ValueError, match=fake_file_name):
            doc.generate(MOCK_CONTEXT, MODULES)

    def test_nonexistent_class_raises(self, sample_mdx: str) -> None:
        # Arrange
        fake_class_name = "NoSuchClass"
        priority = PagePriority(classes=[fake_class_name])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match=fake_class_name):
            doc.generate(MOCK_CONTEXT, MODULES)

    def test_nonexistent_method_raises(self, sample_mdx: str) -> None:
        # Arrange
        fake_method_name = "no_such_method"
        priority = PagePriority(methods={"InfrahubClient": [fake_method_name]})
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match=fake_method_name):
            doc.generate(MOCK_CONTEXT, MODULES)

    def test_nonexistent_section_raises(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(sections=["NoSuchSection"])
        doc = build_ordered_doc(sample_mdx, priority)

        # Act / Assert
        with pytest.raises(ValueError, match="NoSuchSection"):
            doc.generate(MOCK_CONTEXT, MODULES)


class TestValidPriorities:
    def test_valid_config_no_error(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(
            classes=["InfrahubClient"],
            methods={"InfrahubClient": ["save"]},
        )
        doc = build_ordered_doc(sample_mdx, priority)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)

        # Assert
        assert FILE_KEY in result


class TestDuplicatePriorities:
    def test_duplicate_class_names_raises(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="Duplicate class 'InfrahubClient'"):
            PagePriority(classes=["InfrahubClient", "InfrahubClient"])

    def test_duplicate_method_names_raises(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="Duplicate method 'save'"):
            PagePriority(methods={"InfrahubClient": ["save", "save"]})

    def test_duplicate_section_names_raises(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="Duplicate section 'Classes'"):
            PagePriority(sections=["Classes", "Classes"])
