# Implementation Plan: Artifact Content Composition

**Branch**: `infp-504-artifact-composition` | **Date**: 2026-03-20 | **Spec**: [spec.md](spec.md)
**Jira**: INFP-504 | **Epic**: IFC-2275

## Summary

Enable Jinja2 templates to reference and inline rendered content from other artifacts and file objects via new filters (`artifact_content`, `file_object_content`, `from_json`, `from_yaml`). Requires evolving the filter trust model from a binary boolean to a flag-based execution context system, creating a new `InfrahubFilters` class to hold client-dependent filter logic, and extending `Jinja2Template` with an optional client parameter.

## Technical Context

**Language/Version**: Python 3.10-3.13
**Primary Dependencies**: jinja2, httpx, pydantic >=2.0, PyYAML (already available via netutils)
**Storage**: Infrahub object store (REST API)
**Testing**: pytest (`uv run pytest tests/unit/`)
**Target Platform**: SDK library consumed by Prefect workers, CLI, and API server
**Project Type**: Single Python package
**Constraints**: No new external dependencies. Must maintain async/sync dual pattern. Must not break existing filter behavior.

## Key Technical Decisions

### 1. Async Filters via Jinja2 native support (R-001)

The `SandboxedEnvironment` already uses `enable_async=True`. Jinja2's `auto_await` automatically awaits filter return values during `render_async()`. The new content-fetching filters can be `async def` — no bridging needed.

**Required change**: Add `enable_async=True` to the file-based environment (`_get_file_based_environment()`) so async filters work for file-based templates too.

### 2. Flag-based trust model (R-004)

Replace `FilterDefinition.trusted: bool` with `allowed_contexts: ExecutionContext` using Python's `Flag` enum. Three contexts: `CORE` (most restrictive), `WORKER`, `LOCAL` (least restrictive). A backward-compatible `trusted` property preserves existing API.

### 3. Content-type checking for file objects (R-003)

New `ObjectStore.get_file_by_storage_id()` method checks response `content-type` header. Text-based types are allowed; binary types are rejected with a descriptive error.

## Project Structure

### Documentation (this feature)

```text
dev/specs/infp-504-artifact-composition/
├── spec.md                          # Feature specification
├── plan.md                          # This file
├── research.md                      # Phase 0 research findings
├── data-model.md                    # Entity definitions
├── quickstart.md                    # Usage examples
├── contracts/
│   └── filter-interfaces.md         # Filter I/O contracts
└── checklists/
    └── requirements.md              # Quality checklist
```

### Source Code (files to create or modify)

```text
infrahub_sdk/
├── template/
│   ├── __init__.py                  # MODIFY: Jinja2Template (client param, validate context)
│   ├── filters.py                   # MODIFY: ExecutionContext enum, FilterDefinition migration
│   ├── exceptions.py                # MODIFY: Add JinjaFilterError
│   └── infrahub_filters.py          # CREATE: InfrahubFilters class
├── object_store.py                  # MODIFY: Add get_file_by_storage_id()
```

```text
tests/unit/
├── template/
│   ├── test_filters.py              # MODIFY: Tests for new filters and trust model
│   └── test_infrahub_filters.py     # CREATE: Tests for InfrahubFilters
```

## Implementation Order

The 13 Jira tasks under IFC-2275 follow this dependency graph:

```text
Phase 1 (Foundation — no dependencies, can be parallel):
  IFC-2367: JinjaFilterError exception
  IFC-2368: Flag-based trust model (ExecutionContext + FilterDefinition migration)
  IFC-2373: ObjectStore.get_file_by_storage_id()

Phase 2 (Filters — depend on Phase 1):
  IFC-2369: from_json filter (depends on IFC-2367)
  IFC-2370: from_yaml filter (depends on IFC-2367)
  IFC-2371: InfrahubFilters class (depends on IFC-2367)

Phase 3 (Content filters — depend on Phase 2):
  IFC-2372: artifact_content filter (depends on IFC-2371)
  IFC-2374: file_object_content filter (depends on IFC-2371, IFC-2373)

Phase 4 (Integration — depend on Phase 3):
  IFC-2375: Jinja2Template client param + wiring (depends on IFC-2368, IFC-2371, IFC-2372)
  IFC-2376: Filter registration with correct contexts (depends on IFC-2368, IFC-2369, IFC-2370, IFC-2372, IFC-2374)

Phase 5 (Documentation + Server — depend on Phase 4):
  IFC-2377: Documentation (depends on IFC-2376)
  IFC-2378: integrator.py threading [Infrahub server] (depends on IFC-2375)
  IFC-2379: Schema validation [Infrahub server] (depends on IFC-2368)
```

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Jinja2 `auto_await` doesn't work as expected for filters | Low | High | Verify with a minimal test before building on the assumption. Fallback: sync wrapper with thread executor. |
| File-based environment breaks with `enable_async=True` | Low | Medium | File-based env change is isolated and testable. Existing tests will catch regressions. |
| ObjectStore API returns incorrect content-type for file objects | Medium | Low | Already flagged by @wvandeun. The filter will use best-effort content-type checking; can be refined when API is fixed. |
| `validate()` backward compat breaks existing callers | Low | High | Keep `restricted` param with deprecation path. Test all existing call sites. |
