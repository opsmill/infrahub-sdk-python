"""Tests for MDX content reordering."""

from __future__ import annotations

import re

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_reorder import (
    ASection,
    MdxSection,
    OrderedMdxSection,
    PagePriority,
    reorder_mdx_content,
)


def _class_order(content: str) -> list[str]:
    """Extract the order of H3 class names under ``## Classes``."""
    match = re.search(r"^## Classes\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"^### `([^`]+)`", match.group(1), re.MULTILINE)


class TestReorderClasses:
    def test_single_priority_class_moves_to_top(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClient"])

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _class_order(result)
        assert order[0] == "InfrahubClient"

    def test_multiple_priority_classes_in_specified_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClientSync", "InfrahubClient"])

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _class_order(result)
        assert order[0] == "InfrahubClientSync"
        assert order[1] == "InfrahubClient"

    def test_non_priority_classes_retain_original_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubClient"])

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _class_order(result)
        remaining = order[1:]
        assert remaining == ["ProcessRelationsNode", "BaseClient", "InfrahubClientSync"]

    def test_no_priority_config_returns_unchanged(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority()

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert result == sample_mdx

    def test_empty_classes_list_returns_unchanged(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=[])

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert result == sample_mdx

    def test_nonexistent_class_name_ignored(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(classes=["DoesNotExist"])

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _class_order(result)
        assert order == ["ProcessRelationsNode", "BaseClient", "InfrahubClient", "InfrahubClientSync"]

    def test_reorder_page_without_methods(self, sample_mdx_no_methods: str) -> None:
        # Arrange
        priority = PagePriority(classes=["InfrahubNodeMode"])

        # Act
        result = reorder_mdx_content(sample_mdx_no_methods, priority)

        # Assert
        order = _class_order(result)
        assert order == ["InfrahubNodeMode", "RelatedNodeState"]


class TestOrderedMdxSection:
    def _make_ordered(
        self,
        name: str,
        heading_level: int,
        children_lines: list[str],
        priority_names: list[str],
        child_heading_level: int = 3,
    ) -> OrderedMdxSection:
        heading = "#" * heading_level + f" `{name}`"
        section = MdxSection(name=name, heading_level=heading_level, _lines=[heading] + children_lines)
        return OrderedMdxSection(
            section=section,
            priority_names=priority_names,
            child_heading_level=child_heading_level,
        )

    def test_content_returns_reordered_children(self) -> None:
        children = [
            "### `Alpha`\n",
            "Alpha body\n",
            "### `Bravo`\n",
            "Bravo body\n",
            "### `Charlie`\n",
            "Charlie body",
        ]
        ordered = self._make_ordered("Classes", 2, children, priority_names=["Charlie", "Alpha"])

        content = ordered.content
        content_str = "\n".join(content)
        names = re.findall(r"^### `([^`]+)`", content_str, re.MULTILINE)
        assert names == ["Charlie", "Alpha", "Bravo"]

    def test_lines_includes_heading_plus_ordered_content(self) -> None:
        children = [
            "### `A`\n",
            "### `B`\n",
        ]
        ordered = self._make_ordered("Classes", 2, children, priority_names=["B"])

        lines = ordered.lines
        assert lines[0] == "## `Classes`"
        names = re.findall(r"^### `([^`]+)`", "\n".join(lines), re.MULTILINE)
        assert names == ["B", "A"]

    def test_empty_priority_returns_original_content(self) -> None:
        children = ["### `X`\n", "body"]
        ordered = self._make_ordered("Sec", 2, children, priority_names=[])
        base = MdxSection(name="Sec", heading_level=2, _lines=["## `Sec`"] + children)

        assert ordered.content == base.content

    def test_no_children_returns_original_content(self) -> None:
        ordered = self._make_ordered("Sec", 2, ["Just some text"], priority_names=["Anything"])
        base = MdxSection(name="Sec", heading_level=2, _lines=["## `Sec`", "Just some text"])

        assert ordered.content == base.content

    def test_is_asection_subclass(self) -> None:
        section = MdxSection(name="MySection", heading_level=2, _lines=["## `MySection`"])
        ordered = OrderedMdxSection(section=section, priority_names=[], child_heading_level=3)

        assert isinstance(ordered, ASection)
        assert isinstance(section, ASection)
        assert ordered.heading == "## `MySection`"


@pytest.fixture
def sample_mdx() -> str:
    return """\
---
title: client
sidebarTitle: client
---

# `infrahub_sdk.client`

## Functions

### `handle_relogin`

```python
handle_relogin(func: Callable) -> Callable
```

### `handle_relogin_sync`

```python
handle_relogin_sync(func: Callable) -> Callable
```

## Classes

### `ProcessRelationsNode`

Process relations for a node.

### `BaseClient`

Base class for InfrahubClient and InfrahubClientSync

**Methods:**

#### `start_tracking`

```python
start_tracking(self) -> Self
```

#### `set_context_properties`

```python
set_context_properties(self, identifier: str) -> None
```

### `InfrahubClient`

GraphQL Client to interact with Infrahub.

**Methods:**

#### `get_version`

```python
get_version(self) -> str
```

Return the Infrahub version.

#### `create`

```python
create(self, kind: str) -> InfrahubNode
```

#### `get`

```python
get(self, kind: str) -> InfrahubNode
```

#### `get`

```python
get(self, kind: type[SchemaType]) -> SchemaType
```

#### `save`

```python
save(self, node: InfrahubNode) -> None
```

#### `delete`

```python
delete(self, kind: str, id: str) -> None
```

### `InfrahubClientSync`

Synchronous GraphQL Client to interact with Infrahub.

**Methods:**

#### `get_version`

```python
get_version(self) -> str
```

#### `create`

```python
create(self, kind: str) -> InfrahubNodeSync
```
"""


@pytest.fixture
def sample_mdx_no_methods() -> str:
    return """\
---
title: constants
sidebarTitle: constants
---

# `infrahub_sdk.node.constants`

## Classes

### `RelatedNodeState`

State of a related node.

### `InfrahubNodeMode`

Mode of an Infrahub node.
"""
