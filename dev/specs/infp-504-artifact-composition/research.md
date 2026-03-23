# Research: Artifact Content Composition

**Feature**: INFP-504 | **Date**: 2026-03-20

## Research Findings

### R-001: Async-to-Sync Bridge for Jinja2 Filters

**Decision**: Use Jinja2's native async filter support (`auto_await`) — no bridging needed.

**Rationale**: The `SandboxedEnvironment` is already created with `enable_async=True` (template/__init__.py:137), and rendering uses `template.render_async()` (template/__init__.py:122). In Jinja2 async mode, filter call results are wrapped in `auto_await()`, which detects awaitables and awaits them automatically. This means we can register async functions directly as filters.

**Caveat**: The file-based environment (`_get_file_based_environment()` at line 140) does NOT currently set `enable_async=True`. This must be added for async filters to work with file-based templates.

**Alternatives considered**:

- `asyncio.run()`: Cannot be used — we're already inside a running event loop during `render_async()`. Would raise `RuntimeError: This event loop is already running`.
- Thread-based executor: Overly complex, introduces thread safety concerns, and is unnecessary given Jinja2's built-in async support.
- `nest_asyncio`: External dependency, fragile, not needed.

**Evidence**: Jinja2 source code confirms `auto_await` wrapping of filter results in async mode. SDK's existing pytest plugin already uses `asyncio.run()` for a different scenario (sync test runner calling async render), which is a distinct pattern.

### R-002: File Object Content API Path

**Decision**: Use `/api/files/by-storage-id/{storage_id}` endpoint.

**Rationale**: Confirmed by product owner. The `storage_id` alone is sufficient for retrieval. Future endpoints for by-hfid and by-node are anticipated but not in scope.

**Implementation note**: The existing `ObjectStore.get()` uses the path `/api/storage/object/{identifier}`. The file object endpoint is completely different, so a new method is needed rather than parameterizing the existing one.

### R-003: Binary Content Detection for File Objects

**Decision**: Check the `content-type` response header from the API response. Reject non-text content types.

**Rationale**: Artifacts are always plain text (no detection needed). File objects can be any type, but the response `content-type` header reliably indicates the type. The current `ObjectStore.get()` returns `response.text` directly without checking the content type — the new file object method must inspect the header first.

**Text types to allow**: `text/*`, `application/json`, `application/yaml`, `application/x-yaml`. Everything else should be rejected with `JinjaFilterError`.

### R-004: Filter Trust Model Design

**Decision**: Flag-based `ExecutionContext` using Python's `Flag` enum.

**Rationale**: The requirements don't form a clean hierarchy. `artifact_content` must be allowed in WORKER but not LOCAL (no client), while `safe` must be allowed in LOCAL but not WORKER. A flag-based system with an allowlist per filter is the only model that handles all cases without implicit ordering assumptions.

**Design**:

```python
class ExecutionContext(Flag):
    CORE = auto()      # API server computed attributes (most restrictive)
    WORKER = auto()    # Prefect background workers
    LOCAL = auto()     # Local CLI / unrestricted rendering
    ALL = CORE | WORKER | LOCAL
```

```python
@dataclass
class FilterDefinition:
    name: str
    allowed_contexts: ExecutionContext
    source: str
```

**Migration**: `trusted=True` → `allowed_contexts=ALL`, `trusted=False` → `allowed_contexts=LOCAL`. A `trusted` property can be preserved for backward compatibility: `return bool(self.allowed_contexts & ExecutionContext.CORE)`.

### R-005: Existing Netutils Filter Inventory

**Decision**: `from_json` and `from_yaml` do NOT exist in the current filter set.

**Rationale**: Searched all 51 builtin filters and 87 netutils filters in `infrahub_sdk/template/filters.py`. No `from_json`, `from_yaml`, `parse_json`, or `parse_yaml` entries. `tojson` exists (builtin, untrusted) but is the reverse operation. Safe to add without de-duplication concerns.

### R-006: ObjectStore Authentication Error Handling

**Decision**: Reuse the existing pattern from `ObjectStore.get()`.

**Rationale**: `ObjectStore.get()` (object_store.py:34-40) already handles 401/403 by raising `AuthenticationError`. The new filters should catch `AuthenticationError` and wrap it in `JinjaFilterError` with a permission-specific message. No new auth handling logic needed in ObjectStore itself.
