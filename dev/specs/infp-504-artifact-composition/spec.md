# Feature specification: Artifact content composition via Jinja2 filters

**Feature Branch**: `infp-504-artifact-composition`
**Created**: 2026-02-18
**Status**: Draft
**Jira**: INFP-504 (part of INFP-304 Artifact of Artifacts initiative)

## Overview

Enable customers building modular configuration pipelines to compose larger artifacts from smaller sub-artifacts by referencing and inlining rendered artifact content directly inside a Jinja2 transform, without duplicating template logic or GraphQL query fields.

## User scenarios & testing *(mandatory)*

### User story 1 - inline artifact content in a composite template (Priority: P1)

A network engineer maintains separate section-level artifacts for routing policy, interfaces, and base config. They want a composite "startup config" artifact whose Jinja2 template pulls in each section's rendered content via a `storage_id` already present in the GraphQL query result — without copy-pasting template logic.

The template uses `artifact.node.storage_id.value | artifact_content` and the rendered output assembles all sections automatically.

**Why this priority**: This is the primary use case that delivers the modular pipeline capability. Everything else in this feature supports or extends it.

**Independent Test**: A Jinja2 template calling `artifact_content` with a valid storage_id can be rendered against a real or mocked Infrahub instance and the output matches the expected concatenated artifact contents.

**Acceptance Scenarios**:

1. **Given** a `Jinja2Template` constructed with a valid `InfrahubClient` and a template calling `storage_id | artifact_content`, **When** the template is rendered with a data dict containing a valid storage_id string, **Then** the output contains the raw string content fetched from the object store.
2. **Given** the same setup but the storage_id is null or the object store cannot retrieve the content, **When** rendered, **Then** the filter raises a descriptive error indicating the retrieval failure.
3. **Given** a `Jinja2Template` constructed *without* an `InfrahubClient` and a template calling `artifact_content`, **When** rendered, **Then** an error is raised with a message clearly stating that an `InfrahubClient` is required for this filter.
4. **Given** a template using `artifact_content` and `validate(restricted=True)` is called, **Then** a `JinjaTemplateOperationViolationError` is raised, confirming the filter is blocked in local restricted mode.

---

### User story 2 - inline file object content in a composite template (Priority: P2)

A template author needs to embed the content of a stored file object (as distinct from an artifact) into a Jinja2 template. They use `storage_id | file_object_content` and the same injection and error-handling behaviour applies.

**Why this priority**: Mirrors `artifact_content` for the file-object use case; same implementation pattern, lower novelty.

**Independent Test**: A template calling `file_object_content` renders correctly with a valid storage_id, and raises a descriptive error for null or unresolvable storage_ids.

**Acceptance Scenarios**:

1. **Given** a `Jinja2Template` with a client and a valid file-object storage_id, **When** rendered, **Then** the raw file content string is returned.
2. **Given** a null or missing storage_id value, **When** the filter is invoked, **Then** an error is raised with a descriptive message about the retrieval failure.
3. **Given** no client provided to `Jinja2Template`, **When** the filter is invoked, **Then** an error is raised.

---

### User story 3 - parse structured artifact content in a template (Priority: P3)

A template author retrieves a JSON-formatted artifact and needs to traverse its structure as a dict within the template. They chain `storage_id | artifact_content | from_json` to obtain a parsed object, then access fields normally.

**Why this priority**: Unlocks structured composition use cases; depends on `artifact_content` (P1) being in place. `from_json`/`from_yaml` are useful in isolation too.

**Independent Test**: A template chaining `artifact_content | from_json` renders correctly and the output reflects values from parsed JSON fields.

**Acceptance Scenarios**:

1. **Given** a template using `storage_id | artifact_content | from_json`, **When** rendered with a storage_id pointing to valid JSON content, **Then** the template can access keys of the parsed object.
2. **Given** `storage_id | artifact_content | from_yaml`, **When** rendered with YAML content, **Then** the template can access keys of the parsed mapping.
3. **Given** `from_json` or `from_yaml` applied to an empty string (for example, a template variable that is explicitly empty), **When** rendered, **Then** the filter returns an empty dict or appropriate empty value without raising.

---

### User story 4 - security gate blocks filters in computed attributes context (Priority: P1)

The Infrahub API server executes computed attributes locally and must block `artifact_content` and `file_object_content` because no network calls should be made within that context. Prefect workers run inside Infrahub with a client and must be able to use these filters. Other currently-untrusted Jinja2 filters (for example, `safe`, `attr`) must remain subject to their existing restriction rules — this feature must not inadvertently widen their permissions.

The existing single `restricted: bool` parameter on `validate()` is insufficient: flipping it to `False` to permit Infrahub filters would also permit all other untrusted filters. The validation mechanism must be extended to express at least three distinct execution contexts.

**Why this priority**: Preventing these filters from running in the computed attributes context is a hard requirement. Shares P1 priority with User Story 1.

**Independent Test**: Validation in the computed-attributes context raises `JinjaTemplateOperationViolationError` for templates using `artifact_content` or `file_object_content`. Validation in the Prefect-worker context passes for the same templates. Neither context changes the restriction behaviour of other currently-untrusted filters.

**Acceptance Scenarios**:

1. **Given** a template referencing `artifact_content`, **When** validated in the computed-attributes context, **Then** `JinjaTemplateOperationViolationError` is raised.
2. **Given** the same template, **When** validated in the Prefect-worker context with a client-initialised `Jinja2Template`, **Then** validation passes.
3. **Given** a template using an existing untrusted filter (for example, `safe`), **When** validated in the Prefect-worker context, **Then** `JinjaTemplateOperationViolationError` is still raised — the Prefect-worker context does not unlock other untrusted filters.

---

### Edge cases

- What happens if a storage_id value is `None` (Python None) rather than a missing string? Both cases must raise a descriptive error.
- What if the object store raises a network or authentication error mid-render? All error conditions (null storage_id, not-found, auth failure, network failure) raise exceptions — there is no silent fallback.
- What if `from_json` or `from_yaml` already exists in the netutils filter set? De-duplicate rather than shadow.
- What happens when `from_json` or `from_yaml` receives malformed content (invalid JSON/YAML syntax)? `JinjaFilterError` is raised — no silent fallback.
- What if the same filter name is registered twice (for example, a user-supplied filter that shadows `artifact_content`)? Existing override behaviour should be preserved.
- File-based templates use a regular `Environment` (not sandboxed); the new filters must be injected correctly in both cases.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: `Jinja2Template.__init__` MUST accept an optional `client` parameter of type `InfrahubClient | None` (default `None`). `InfrahubClientSync` is not supported.
- **FR-002**: A dedicated class (for example, `InfrahubFilters`) MUST be introduced to hold the client reference and expose the Infrahub-specific filter callable methods. `Jinja2Template` instantiates this class when a client is provided and registers its filters into the Jinja2 environment.
- **FR-003**: The system MUST provide an `artifact_content` Jinja2 filter that accepts a `storage_id` string and returns the raw string content of the referenced artifact, using the artifact-specific API path.
- **FR-004**: The system MUST provide a `file_object_content` Jinja2 filter that accepts a `storage_id` string and returns the raw string content of the referenced file object, using the file-object-specific API path or metadata handling — this implementation is distinct from `artifact_content`.
- **FR-005**: Both `artifact_content` and `file_object_content` MUST raise `JinjaFilterError` when the input `storage_id` is null or empty, or when the object store cannot retrieve the content for any reason (not found, network failure, auth failure).
- **FR-006**: Both `artifact_content` and `file_object_content` MUST raise `JinjaFilterError` when invoked and no `InfrahubClient` was supplied to `Jinja2Template` at construction time. The error message MUST name the filter and explain that an `InfrahubClient` is required.
- **FR-007**: Both `artifact_content` and `file_object_content` MUST be registered with `trusted=False` in the `FilterDefinition` registry so that `validate(restricted=True)` blocks them in the computed attributes execution context (Infrahub API server). They are only permitted to execute on Prefect workers, where an `InfrahubClient` is available. Within Infrahub any Jinja2 based computed attributes that use these new filters should cause a schema violation when loading the schema.
- **FR-008**: The system MUST provide `from_json` and `from_yaml` Jinja2 filters (adding them only if not already present in the environment) that parse a string into a Python dict/list. Applying them to an empty string MUST return an empty dict without raising. Applying them to malformed content MUST raise `JinjaFilterError`.
- **FR-009**: `from_json` and `from_yaml` MUST be registered as trusted filters (`trusted=True`) since they perform no external I/O.
- **FR-010**: All new filters MUST work correctly with `InfrahubClient` (async). `InfrahubClientSync` is not a supported client type for `Jinja2Template`.
- **FR-011**: All `JinjaFilterError` instances MUST carry an actionable error message that identifies the filter name, the cause of failure, and any remediation hint (for example: "artifact_content requires an InfrahubClient — pass one via Jinja2Template(client=...)").
- **FR-012**: A new `JinjaFilterError` exception class MUST be added to `infrahub_sdk/template/exceptions.py` as a subclass of `JinjaTemplateError`.
- **FR-013**: Documentation MUST include a Python transform example demonstrating artifact content retrieval via `client.object_store.get(identifier=storage_id)`. No new SDK convenience method will be added.
- **FR-014**: If the current user isn't allowed due to a permission denied error to query for the artifact or object file the filter should catch such permission error and raise a Jinja2 error specifically related to the permission issue.

### Key entities

- **`Jinja2Template`**: Gains an optional `client` constructor parameter; delegates client-bound filter registration to `InfrahubFilters`.
- **`InfrahubFilters`**: New class that holds an `InfrahubClient` reference and exposes `artifact_content`, `file_object_content`, and any other client-dependent filter methods. Registered into the Jinja2 filter map when a client is provided.
- **`FilterDefinition`**: Existing dataclass used to declare filter `name`, `trusted` flag, and `source`. New entries are added here for all new filters.
- **`ObjectStore` / `ObjectStoreSync`**: Existing async/sync storage clients used by `InfrahubFilters` to perform `get(identifier=storage_id)` calls.
- **`JinjaFilterError`**: New exception class, subclass of `JinjaTemplateError`, raised by `InfrahubFilters` methods on all filter-level failures (no client, null/empty storage_id, retrieval error).

## Success criteria *(mandatory)*

### Measurable outcomes

- **SC-001**: A composite Jinja2 artifact template using `artifact_content` renders successfully end-to-end (integration test), with output containing all expected sub-artifact content.
- **SC-002**: `validate(restricted=True)` on any template referencing `artifact_content` or `file_object_content` always raises a security violation — zero false negatives across the test suite.
- **SC-003**: All filter error conditions (no client, null/empty storage_id, retrieval failure) produce a descriptive, actionable error message — no silent failures, no raw tracebacks as the primary user-facing message.
- **SC-004**: The async execution path (`InfrahubClient`) is covered by unit tests with no regressions to existing filter behaviour.
- **SC-005**: The full unit test suite (`uv run pytest tests/unit/`) passes without modification after the feature is added.
- **SC-006**: A template chaining `artifact_content | from_json` or `artifact_content | from_yaml` can access parsed fields from a structured artifact in a rendered output.

## Assumptions

- The `artifact_content` and `file_object_content` filters receive a `storage_id` string directly from the template variable context — extracted from the GraphQL query result by the template author. The filter does not resolve artifact names — it operates on storage IDs only.
- Ordering of artifact generation is a known limitation: artifacts may be generated in parallel. This is a documented constraint, not something this feature enforces. Future event-driven pipeline work (INFP-227) will address ordering.
- `from_json` and `from_yaml` are not currently present in the builtin or netutils filter sets; they will be added as part of this feature. If they already exist, the implementation de-duplicates rather than overrides.
- All failure modes from the filters (null storage_id, empty storage_id, object not found, network error, auth error) raise exceptions. There is no silent fallback to an empty string.
- The permitted execution context for `artifact_content` and `file_object_content` is Prefect workers only. The computed attributes path in the Infrahub API server always runs `validate(restricted=True)`, which blocks these filters before rendering begins.
- The `InfrahubFilters` class provides synchronous callables to Jinja2's filter map; the underlying client is always `InfrahubClient` (async). Async I/O calls are handled consistently with the SDK's existing pattern.

## Dependencies & constraints

- Depends on `ObjectStore.get(identifier)` in `infrahub_sdk/object_store.py`.
- Depends on the existing `FilterDefinition` dataclass and `trusted` flag mechanism in `infrahub_sdk/template/filters.py`.
- Depends on the existing `validate(restricted=True)` security mechanism in `Jinja2Template`.
- Must not break any existing filter behaviour or the `validate()` contract.
- No new external Python dependencies may be introduced without approval.
- Related: INFP-304 (Artifact of Artifacts), INFP-496 (Modular GraphQL queries), INFP-227 (Modular generators / event-driven pipeline).

## Open questions

- **Filter naming**: `artifact_content` is the working name. Alternatives are open. Same with `file_object_content` as one option is to use the "/api/storage/files/by-storage-id" endpoint, we will want to support "by-hfid" and node as well.
- **Sandboxed environment injection**: The `render_jinja2_template` method in `integrator.py` has access to `self.sdk`; the exact threading path to pass the client into `Jinja2Template` needs investigation during planning.
- **Validation level model**: The current `validate(restricted: bool)` parameter is too coarse to express the three distinct execution contexts this feature requires. A natural evolution would be to replace the boolean with an enum (for example: `core` for the Infrahub API server, `worker` for Prefect background workers, `untrusted` for fully restricted local execution). Filters tagged as `worker`-only would be blocked in the `core` context but permitted in the `worker` context, while `trusted` filters remain available in all contexts. The exact enum design and migration of existing call sites is a technical decision for the implementation plan, but the interface change should be considered up front to avoid needing to revisit `validate()` again later.

## Clarifications

### Session 2026-02-18

- Q: Are `artifact_content` and `file_object_content` identical at the storage API level, or do they use different API paths / metadata handling? → A: Different implementations — `file_object_content` uses a different API path or carries different metadata handling than `artifact_content`.
- Q: Where are these filters permitted to execute, and what mechanism enforces the boundary? → A: Blocked in computed attributes (executed locally in the Infrahub API server, which uses `validate(restricted=True)`); permitted on Prefect workers, which have access to an `InfrahubClient`. The `trusted=False` registration enforces this boundary via the existing restricted-mode validation.
- Q: What exception class should filter-level errors (no client, retrieval failure) raise? → A: A new `JinjaFilterError` class that is a child of the existing `JinjaTemplateError` base class.
- Q: Should the SDK expose a convenience method for artifact content retrieval in Python transforms? → A: No new method — document `client.object_store.get(identifier=storage_id)` directly.
- Q: What should `from_json`/`from_yaml` do on malformed input? → A: Raise `JinjaFilterError` on malformed JSON or YAML input.
