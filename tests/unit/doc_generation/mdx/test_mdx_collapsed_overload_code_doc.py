"""Tests for CollapsedOverloadCodeDocumentation pipeline decorator."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import MdxFile
from docs.docs_generation.content_gen_methods.mdx.mdx_collapsed_overload_code_doc import (
    CollapsedOverloadCodeDocumentation,
)

from .conftest import FILE_KEY, MOCK_CONTEXT, MODULES, StubDocumentation


class TestCollapseOverloads:
    def test_overloaded_methods_collapsed_to_primary_plus_details(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        visible_part = result.split("<details>")[0]
        assert visible_part.count("#### `get`") == 1
        assert "<details>" in result

    def test_non_overloaded_methods_unchanged(self, sample_mdx_no_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_no_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == sample_mdx_no_overloads

    def test_mixed_overloaded_and_non_overloaded(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert "#### `get`" in result
        assert "#### `create`" in result
        assert "#### `delete`" in result
        assert result.count("<details>") == 2

    def test_primary_is_overload_with_most_params(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert "timeout" in result

    def test_details_label_shows_correct_count(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert "Show 2 other overloads" in result

    def test_singular_label_for_two_overloads(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert "Show 1 other overload" in result


class TestNoOverloads:
    def test_empty_content_passes_through(self) -> None:
        # Arrange
        content = "# minimal"
        doc = _build_collapsed_doc(content)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == content


def _build_collapsed_doc(content: str) -> CollapsedOverloadCodeDocumentation:
    """Build a ``CollapsedOverloadCodeDocumentation`` with a stub inner documentation."""
    inner = StubDocumentation({FILE_KEY: MdxFile(name=FILE_KEY, content=content, source_path=Path("test.py"))})
    return CollapsedOverloadCodeDocumentation(documentation=inner)


# --- Fixtures ---


@pytest.fixture
def sample_mdx_no_overloads() -> str:
    return """\
---
title: test
---

# `test_module`

## Classes

### `MyClass`

A simple class.

**Methods:**

#### `save`

```python
save(self, data: str) -> None
```

#### `delete`

```python
delete(self, id: str) -> None
```"""


@pytest.fixture
def sample_mdx_with_overloads() -> str:
    return """\
---
title: client
sidebarTitle: client
---

# `infrahub_sdk.client`

## Classes

### `InfrahubClient`

GraphQL Client to interact with Infrahub.

**Methods:**

#### `get`

```python
get(self, kind: str) -> InfrahubNode
```

#### `get`

```python
get(self, kind: type[SchemaType]) -> SchemaType
```

#### `get`

```python
get(self, kind: str | type[SchemaType], raise_when_missing: bool = True) -> InfrahubNode | SchemaType | None
```

#### `create`

```python
create(self, kind: str) -> InfrahubNode
```

#### `create`

```python
create(self, kind: str, data: dict | None = None, branch: str | None = None, timeout: int | None = None) -> InfrahubNode
```

#### `delete`

```python
delete(self, kind: str, id: str) -> None
```"""
