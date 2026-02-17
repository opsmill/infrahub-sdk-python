"""Tests for CollapsedOverloadCodeDocumentation pipeline decorator."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import ACodeDocumentation, MdxFile
from docs.docs_generation.content_gen_methods.mdx.mdx_collapsed_overload_code_doc import (
    CollapsedOverloadCodeDocumentation,
)

if TYPE_CHECKING:
    from invoke import Context

FILE_KEY = "test.mdx"
MOCK_CONTEXT = MagicMock(spec="Context")
MODULES: list[str] = []


class TestCollapseOverloads:
    def test_overloaded_methods_collapsed_to_primary_plus_details(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        get_headings = _method_headings(result, "InfrahubClient")
        assert get_headings.count("get") == 1
        assert _has_details_block(result, "get")

    def test_non_overloaded_methods_unchanged(self) -> None:
        # Arrange
        content = """\
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
        doc = _build_collapsed_doc(content)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == content

    def test_mixed_overloaded_and_non_overloaded(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        methods = _method_headings(result, "InfrahubClient")
        assert methods.count("get") == 1
        assert methods.count("create") == 1
        assert methods.count("delete") == 1
        assert _has_details_block(result, "get")
        assert _has_details_block(result, "create")
        assert not _has_details_block(result, "delete")

    def test_primary_is_overload_with_most_params(self, sample_mdx_with_overloads: str) -> None:
        # Arrange
        doc = _build_collapsed_doc(sample_mdx_with_overloads)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        primary_sig = _primary_signature(result, "InfrahubClient", "create")
        assert "timeout" in primary_sig

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

    def test_file_without_classes_returned_unchanged(self) -> None:
        # Arrange
        content = """\
---
title: test
---

# `test_module`

## Functions

### `helper_func`

```python
helper_func(x: int) -> str
```"""
        doc = _build_collapsed_doc(content)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == content

    def test_multiple_classes_each_collapsed_independently(self) -> None:
        # Arrange
        content = """\
---
title: test
---

# `test_module`

## Classes

### `ClassA`

**Methods:**

#### `run`

```python
run(self, x: int) -> None
```

#### `run`

```python
run(self, x: int, y: int) -> None
```

### `ClassB`

**Methods:**

#### `execute`

```python
execute(self, a: str) -> None
```

#### `execute`

```python
execute(self, a: str, b: str) -> None
```"""
        doc = _build_collapsed_doc(content)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert _has_details_block(result, "run")
        assert _has_details_block(result, "execute")
        assert result.count("Show 1 other overload") == 2


class TestNoOverloads:
    def test_empty_content_passes_through(self) -> None:
        # Arrange
        content = "# minimal"
        doc = _build_collapsed_doc(content)

        # Act
        result = doc.generate(MOCK_CONTEXT, MODULES)[FILE_KEY].content

        # Assert
        assert result == content


# --- Helpers ---


class _StubDocumentation(ACodeDocumentation):
    """Minimal stub returning pre-built MdxFile dicts."""

    def __init__(self, files: dict[str, MdxFile]) -> None:
        self._files = files

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        return self._files


def _build_collapsed_doc(content: str) -> CollapsedOverloadCodeDocumentation:
    """Build a ``CollapsedOverloadCodeDocumentation`` with a stub inner documentation."""
    inner = _StubDocumentation({FILE_KEY: MdxFile(name=FILE_KEY, content=content, source_path=Path("test.py"))})
    return CollapsedOverloadCodeDocumentation(documentation=inner)


def _method_headings(content: str, class_name: str) -> list[str]:
    """Extract H4 method names under a given H3 class section, excluding those inside details blocks."""
    pattern = rf"^### `{re.escape(class_name)}`\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    section = match.group(1)
    in_details = False
    methods: list[str] = []
    for line in section.split("\n"):
        if "<details>" in line:
            in_details = True
        elif "</details>" in line:
            in_details = False
        elif not in_details:
            m = re.match(r"^#### `([^`]+)`", line)
            if m:
                methods.append(m.group(1))
    return methods


def _has_details_block(content: str, method_name: str) -> bool:
    """Check if a <details> block exists near a method heading."""
    pattern = rf"#### `{re.escape(method_name)}`.*?(?=#### |### |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return False
    return "<details>" in match.group(0)


def _primary_signature(content: str, class_name: str, method_name: str) -> str:
    """Extract the primary (visible, not inside details) signature for a method."""
    pattern = rf"^### `{re.escape(class_name)}`\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    section = match.group(1)
    in_details = False
    capture_next_fence = False
    for line in section.split("\n"):
        if "<details>" in line:
            in_details = True
        elif "</details>" in line:
            in_details = False
        elif not in_details and re.match(rf"^#### `{re.escape(method_name)}`", line):
            capture_next_fence = True
        elif capture_next_fence and line.startswith("```python"):
            capture_next_fence = False
        elif capture_next_fence is False and not in_details and line and not line.startswith("```"):
            if "(" in line:
                return line
            capture_next_fence = None
    return ""


# --- Fixtures ---


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
