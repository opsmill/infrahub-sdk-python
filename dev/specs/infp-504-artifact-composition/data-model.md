# Data Model: Artifact Content Composition

**Feature**: INFP-504 | **Date**: 2026-03-20

## New Entities

### ExecutionContext (Flag enum)

**Location**: `infrahub_sdk/template/filters.py`

```python
class ExecutionContext(Flag):
    CORE = auto()      # API server computed attributes — most restrictive
    WORKER = auto()    # Prefect background workers
    LOCAL = auto()     # Local CLI / unrestricted rendering
    ALL = CORE | WORKER | LOCAL
```

**Semantics**: Represents where template code executes. A filter's `allowed_contexts` flags are an allowlist — fewer flags means less trusted.

### FilterDefinition (modified)

**Location**: `infrahub_sdk/template/filters.py`

```python
@dataclass
class FilterDefinition:
    name: str
    allowed_contexts: ExecutionContext
    source: str

    @property
    def trusted(self) -> bool:
        """Backward compatibility: trusted means allowed in all contexts."""
        return self.allowed_contexts == ExecutionContext.ALL
```

**Migration**:

| Current | New |
| ------- | --- |
| `FilterDefinition("abs", trusted=True, source="jinja2")` | `FilterDefinition("abs", allowed_contexts=ExecutionContext.ALL, source="jinja2")` |
| `FilterDefinition("safe", trusted=False, source="jinja2")` | `FilterDefinition("safe", allowed_contexts=ExecutionContext.LOCAL, source="jinja2")` |

### JinjaFilterError (new exception)

**Location**: `infrahub_sdk/template/exceptions.py`

```python
class JinjaFilterError(JinjaTemplateError):
    def __init__(self, filter_name: str, message: str, hint: str | None = None) -> None:
        self.filter_name = filter_name
        self.hint = hint
        full_message = f"Filter '{filter_name}': {message}"
        if hint:
            full_message += f" — {hint}"
        super().__init__(full_message)
```

**Inheritance**: `Error` → `JinjaTemplateError` → `JinjaFilterError`

### InfrahubFilters (new class)

**Location**: `infrahub_sdk/template/infrahub_filters.py` (new file)

```python
class InfrahubFilters:
    @classmethod
    def get_filter_names(cls) -> tuple[str, ...]:
        """Discover filter names from public methods."""
        ...

    def __init__(self, client: InfrahubClient | None = None) -> None:
        self.client = client

    def _require_client(self, filter_name: str) -> InfrahubClient:
        """Raise JinjaFilterError if no client is available."""
        ...

    async def artifact_content(self, storage_id: str) -> str: ...
    async def file_object_content(self, storage_id: str) -> str: ...
    async def file_object_content_by_id(self, node_id: str) -> str: ...
    async def file_object_content_by_hfid(self, hfid: str | list[str], kind: str = "") -> str: ...
```

**Key design decisions**:

- Client is optional — `InfrahubFilters` is always instantiated, each method checks for a client at call time via `_require_client()`
- `get_filter_names()` discovers client-dependent filter names automatically from all public methods — adding a new filter only requires adding a method
- Methods are `async` — Jinja2's `auto_await` handles them in async rendering mode
- Holds an `InfrahubClient` (async only), not `InfrahubClientSync`
- Each method validates inputs and catches `AuthenticationError` to wrap in `JinjaFilterError`
- File object retrieval is split into 3 filters matching the server's 3 endpoints (`by-storage-id`, `by-id`, `by-hfid`)

## Modified Entities

### Jinja2Template (modified constructor)

**Location**: `infrahub_sdk/template/__init__.py`

```python
def __init__(
    self,
    template: str | Path,
    template_directory: Path | None = None,
    filters: dict[str, Callable] | None = None,
    client: InfrahubClient | None = None,  # NEW
) -> None:
```

**Changes**:

- New optional `client` parameter
- When `client` provided: instantiate `InfrahubFilters`, register `artifact_content` and `file_object_content`
- Always register `from_json` and `from_yaml` (no client needed)
- File-based environment already has `enable_async=True` (no change needed)

### Jinja2Template.set_client() (new method)

```python
def set_client(self, client: InfrahubClient) -> None:
```

**Purpose**: Deferred client injection — allows creating a `Jinja2Template` first and adding the client later. Also supports replacing a previously set client.

- Updates `self._infrahub_filters.client` on the existing `InfrahubFilters` instance (no re-registration needed since the bound methods are already registered)
- If the Jinja2 environment was already created, patches it in place
- Without calling `set_client()` (and without passing `client` to `__init__`), client-dependent filters raise `JinjaFilterError` with a descriptive message at render time via `_require_client()`

### Jinja2Template.validate() (modified signature)

```python
def validate(self, restricted: bool = True, context: ExecutionContext | None = None) -> None:
```

**Changes**:

- New optional `context` parameter (takes precedence over `restricted` when provided)
- Backward compat: `restricted=True` → `ExecutionContext.CORE`, `restricted=False` → `ExecutionContext.LOCAL`
- Validation logic: filter allowed if `filter.allowed_contexts & context` is truthy

### ObjectStore (new method)

**Location**: `infrahub_sdk/object_store.py`

```python
async def get_file_by_storage_id(self, storage_id: str, tracker: str | None = None) -> str:
    """Retrieve file object content by storage_id.

    Raises error if content-type is not text-based.
    """
    ...
```

**API endpoints**:

- `GET /api/files/by-storage-id/{storage_id}` — used by `file_object_content`
- `GET /api/files/{node_id}` — used by `file_object_content_by_id`
- `GET /api/files/by-hfid/{kind}?hfid=...` — used by `file_object_content_by_hfid`

**Content-type check**: Allow `text/*`, `application/json`, `application/yaml`, `application/x-yaml`. Reject all others.

## New Filter Registrations

```python
# In AVAILABLE_FILTERS:

# Infrahub client-dependent filters (worker and local contexts)
FilterDefinition("artifact_content", allowed_contexts=ExecutionContext.WORKER | ExecutionContext.LOCAL, source="infrahub"),
FilterDefinition("file_object_content", allowed_contexts=ExecutionContext.WORKER | ExecutionContext.LOCAL, source="infrahub"),
FilterDefinition("file_object_content_by_hfid", allowed_contexts=ExecutionContext.WORKER | ExecutionContext.LOCAL, source="infrahub"),
FilterDefinition("file_object_content_by_id", allowed_contexts=ExecutionContext.WORKER | ExecutionContext.LOCAL, source="infrahub"),

# Parsing filters (trusted, all contexts)
FilterDefinition("from_json", allowed_contexts=ExecutionContext.ALL, source="infrahub"),
FilterDefinition("from_yaml", allowed_contexts=ExecutionContext.ALL, source="infrahub"),
```

## Relationships

```text
Jinja2Template
  ├── has-a → InfrahubFilters (when client provided)
  ├── uses → FilterDefinition registry (for validation)
  └── uses → ExecutionContext (for context-aware validation)

InfrahubFilters
  ├── has-a → InfrahubClient
  └── uses → ObjectStore (for content retrieval)

JinjaFilterError
  └── extends → JinjaTemplateError → Error
```
