"""Shared fixtures and helpers for OrderedMdxCodeDocumentation tests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import ACodeDocumentation, MdxFile
from docs.docs_generation.content_gen_methods.mdx.mdx_ordered_code_doc import OrderedMdxCodeDocumentation

if TYPE_CHECKING:
    from invoke import Context

    from docs.docs_generation.content_gen_methods.mdx.mdx_priority import PagePriority

FILE_KEY = "test.mdx"
MOCK_CONTEXT = MagicMock(spec="Context")
MODULES: list[str] = []


# --- Helpers ---


class StubDocumentation(ACodeDocumentation):
    """Minimal stub returning pre-built MdxFile dicts."""

    def __init__(self, files: dict[str, MdxFile]) -> None:
        self._files = files

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        return self._files


def build_ordered_doc(content: str, priority: PagePriority) -> OrderedMdxCodeDocumentation:
    """Build an ``OrderedMdxCodeDocumentation`` with a stub inner documentation."""
    inner = StubDocumentation({FILE_KEY: MdxFile(name=FILE_KEY, content=content, source_path=Path("test.py"))})
    return OrderedMdxCodeDocumentation(documentation=inner, page_priorities={FILE_KEY: priority})


def section_order(content: str) -> list[str]:
    """Extract the order of H2 section names."""
    return re.findall(r"^## (\w+)", content, re.MULTILINE)


def class_order(content: str) -> list[str]:
    """Extract the order of H3 class names under ``## Classes``."""
    match = re.search(r"^## Classes\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"^### `([^`]+)`", match.group(1), re.MULTILINE)


def method_order(content: str, class_name: str) -> list[str]:
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
