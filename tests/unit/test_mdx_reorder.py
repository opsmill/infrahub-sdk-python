"""Tests for MDX content reordering."""

from __future__ import annotations

import re

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority
from docs.docs_generation.content_gen_methods.mdx.mdx_reorder import reorder_mdx_content


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


class TestReorderMethods:
    def test_single_priority_method_moves_to_top(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert _method_order(result, "InfrahubClient")[0] == "save"

    def test_multiple_priority_methods_in_specified_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["delete", "save"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _method_order(result, "InfrahubClient")
        assert order[0] == "delete"
        assert order[1] == "save"

    def test_non_priority_methods_retain_original_order(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _method_order(result, "InfrahubClient")
        assert order[0] == "save"
        assert order[1:] == ["get_version", "create", "get", "get", "delete"]

    def test_method_only_priority_no_class_reordering(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["save"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert _class_order(result) == ["ProcessRelationsNode", "BaseClient", "InfrahubClient", "InfrahubClientSync"]

    def test_combined_class_and_method_reordering(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(
            classes=["InfrahubClient"],
            methods={"InfrahubClient": ["save"]},
        )

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert _class_order(result)[0] == "InfrahubClient"
        assert _method_order(result, "InfrahubClient")[0] == "save"

    def test_overloaded_methods_move_together(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["get"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        order = _method_order(result, "InfrahubClient")
        assert order[0] == "get"
        assert order[1] == "get"
        assert order[2:] == ["get_version", "create", "save", "delete"]

    def test_nonexistent_method_name_ignored(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"InfrahubClient": ["nonexistent", "save"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert _method_order(result, "InfrahubClient")[0] == "save"

    def test_method_priority_for_nonexistent_class_ignored(self, sample_mdx: str) -> None:
        # Arrange
        priority = PagePriority(methods={"DoesNotExist": ["get"]})

        # Act
        result = reorder_mdx_content(sample_mdx, priority)

        # Assert
        assert result == sample_mdx


# --- Helpers ---


def _class_order(content: str) -> list[str]:
    """Extract the order of H3 class names under ``## Classes``."""
    match = re.search(r"^## Classes\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"^### `([^`]+)`", match.group(1), re.MULTILINE)


def _method_order(content: str, class_name: str) -> list[str]:
    """Extract the order of H4 method names under a given H3 class section."""
    pattern = rf"^### `{re.escape(class_name)}`\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"^#### `([^`]+)`", match.group(1), re.MULTILINE)


# --- Fixtures ---


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
