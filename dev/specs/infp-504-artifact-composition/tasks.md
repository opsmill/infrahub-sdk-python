# Tasks: Artifact Content Composition via Jinja2 Filters

**Input**: Design documents from `dev/specs/infp-504-artifact-composition/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Jira Epic**: IFC-2275

**Tests**: Included with each implementation task (per project convention).

**Organization**: Tasks grouped by user story. US4 (security gate) is foundational and combined with US1 as both are P1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Exception class and trust model that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T001 [P] Create `JinjaFilterError` exception class in `infrahub_sdk/template/exceptions.py` — subclass of `JinjaTemplateError` with `filter_name`, `message`, and optional `hint` attributes. Include unit tests for instantiation, inheritance chain, and message formatting. (IFC-2367)
- [x] T002 [P] Implement `ExecutionContext` flag enum and migrate `FilterDefinition` in `infrahub_sdk/template/filters.py` — add `ExecutionContext(Flag)` with `CORE`, `WORKER`, `LOCAL`, `ALL` values. Replace `FilterDefinition.trusted: bool` with `allowed_contexts: ExecutionContext`. Add backward-compat `trusted` property. Migrate all 138 existing filter entries (`trusted=True` → `ALL`, `trusted=False` → `LOCAL`). Update `validate()` in `infrahub_sdk/template/__init__.py` to accept optional `context: ExecutionContext` parameter (takes precedence over `restricted`; `restricted=True` → `CORE`, `restricted=False` → `LOCAL`). Include unit tests for all 3 contexts with existing filters, backward compat path, and no regressions. (IFC-2368)

**Checkpoint**: Foundation ready — JinjaFilterError and ExecutionContext available for all stories

---

## Phase 2: US1 — Inline Artifact Content + US4 — Security Gate (Priority: P1) MVP

**Goal**: A Jinja2 template can use `storage_id | artifact_content` to inline rendered sub-artifact content. Validation blocks this filter in CORE context but allows it in WORKER context.

**Independent Test**: Render a template calling `artifact_content` with a mocked `InfrahubClient` and verify output matches expected content. Validate the same template in CORE context raises `JinjaTemplateOperationViolationError`, and in WORKER context passes.

### Implementation for US1 + US4

- [x] T003 [US1] Create `InfrahubFilters` class in `infrahub_sdk/template/infrahub_filters.py` — new file. Class holds `InfrahubClient` reference, exposes async filter methods. Methods are `async def` (Jinja2 `auto_await` handles them in async render mode per R-001). Raises `JinjaFilterError` when called without a client. Include unit tests for instantiation with/without client. (IFC-2371)
- [x] T004 [US1] Implement `artifact_content` async method on `InfrahubFilters` in `infrahub_sdk/template/infrahub_filters.py` — uses `self.client.object_store.get(identifier=storage_id)`. Raises `JinjaFilterError` on: null/empty storage_id, retrieval failure, permission denied (catch `AuthenticationError` per R-006). Artifacts are always text (no binary check needed per R-003). Include unit tests: happy path (mocked ObjectStore), null, empty, not-found, network error, permission denied, no-client error with descriptive message. (IFC-2372)
- [x] T005 [US1] [US4] Add `client` parameter to `Jinja2Template.__init__` and wire up filter registration in `infrahub_sdk/template/__init__.py` — add `client: InfrahubClient | None = None` param. When client provided: instantiate `InfrahubFilters`, register `artifact_content` into Jinja2 env filter map. Add `enable_async=True` to `_get_file_based_environment()` (per R-001 caveat). Register `artifact_content` in `FilterDefinition` registry with `allowed_contexts=ExecutionContext.WORKER`. Include unit tests: render with client (mocked), render without client (error), validation in CORE (blocked), WORKER (allowed), LOCAL (allowed). Verify existing untrusted filters like `safe` remain blocked in WORKER context (US4 AC3). Also added `set_client()` setter for deferred client injection per PR #885 feedback. (IFC-2375 partial + IFC-2376 partial)

**Checkpoint**: US1 + US4 fully functional. `artifact_content` renders in WORKER context, blocked in CORE. MVP complete.

---

## Phase 3: US2 — Inline File Object Content (Priority: P2)

**Goal**: A Jinja2 template can use `storage_id | file_object_content` to inline file object content with binary rejection.

**Independent Test**: Render a template calling `file_object_content` with a mocked client. Verify text content returned, binary content rejected. Validation blocks in CORE, allows in WORKER.

### Implementation for US2

- [x] T006 [P] [US2] Add `get_file_by_storage_id()` method to `ObjectStore` in `infrahub_sdk/object_store.py` — async method using endpoint `GET /api/files/by-storage-id/{storage_id}`. Check `content-type` response header: allow `text/*`, `application/json`, `application/yaml`, `application/x-yaml`; reject all others with descriptive error. Handle 401/403 as `AuthenticationError`. Include unit tests: text response, binary rejection, 404, auth failure, network error. (IFC-2373)
- [x] T007 [US2] Implement `file_object_content` async method on `InfrahubFilters` in `infrahub_sdk/template/infrahub_filters.py` — uses new `self.client.object_store.get_file_by_storage_id(storage_id)`. Same error handling as `artifact_content` plus binary content error (delegated to ObjectStore). Include unit tests: happy path, all error conditions, binary content rejection. (IFC-2374)
- [x] T008 [US2] Register `file_object_content` filter in `Jinja2Template` and `FilterDefinition` in `infrahub_sdk/template/__init__.py` and `infrahub_sdk/template/filters.py` — register when client provided. `allowed_contexts=ExecutionContext.WORKER`. Include unit tests: render with client, validation in CORE (blocked), WORKER (allowed). (IFC-2375 partial + IFC-2376 partial)

**Checkpoint**: US2 complete. `file_object_content` works alongside `artifact_content`.

---

## Phase 4: US3 — Parse Structured Artifact Content (Priority: P3)

**Goal**: Templates can chain `artifact_content | from_json` or `artifact_content | from_yaml` to access structured data.

**Independent Test**: Render a template chaining `artifact_content | from_json` and verify parsed fields accessible. `from_json("")` and `from_yaml("")` return `{}`.

### Implementation for US3

- [ ] T009 [P] [US3] Implement `from_json` filter function in `infrahub_sdk/template/infrahub_filters.py` — pure sync function (no client needed). Empty string → `{}` (explicit special-case since `json.loads("")` raises). Malformed JSON → `JinjaFilterError`. Register in `FilterDefinition` with `allowed_contexts=ExecutionContext.ALL`. Register unconditionally in `Jinja2Template._set_filters()`. Include unit tests: valid JSON dict, valid JSON list, empty string → `{}`, malformed → error, render through template. (IFC-2369)
- [ ] T010 [P] [US3] Implement `from_yaml` filter function in `infrahub_sdk/template/infrahub_filters.py` — pure sync function. Empty string → `{}` (explicit special-case since `yaml.safe_load("")` returns `None`). Malformed YAML → `JinjaFilterError`. Register in `FilterDefinition` with `allowed_contexts=ExecutionContext.ALL`. Register unconditionally in `Jinja2Template._set_filters()`. Include unit tests: valid YAML mapping, valid YAML list, empty string → `{}`, malformed → error, render through template. (IFC-2370)
- [ ] T011 [US3] Integration test for filter chaining in `tests/unit/template/test_infrahub_filters.py` — test `artifact_content | from_json` and `artifact_content | from_yaml` end-to-end with mocked ObjectStore returning JSON/YAML content. Verify template can access parsed fields. (IFC-2376 partial, SC-006)

**Checkpoint**: US3 complete. All 4 filters work, chain correctly, and are validated per context.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, full regression, and server-side tasks

- [ ] T012 Run full unit test suite (`uv run pytest tests/unit/`) and verify zero regressions (SC-005)
- [ ] T013 Run `uv run invoke format lint-code` and fix any issues
- [ ] T014 Documentation: artifact composition usage guide — create or update docs with Jinja2 filter examples, Python transform example using `client.object_store.get(identifier=storage_id)`, GraphQL query patterns, known limitations (no ordering guarantee). Run `uv run invoke docs-generate` and `uv run invoke docs-validate`. (IFC-2377)
- [ ] T015 [Infrahub server] Thread SDK client into `Jinja2Template` in `integrator.py` — pass `self.sdk` from `render_jinja2_template` as `Jinja2Template(client=...)` on Prefect workers. Integration test with composite template. (IFC-2378)
- [ ] T016 [Infrahub server] Schema validation: block new filters in computed attributes — validate with `context=ExecutionContext.CORE` at schema load time. Templates using `artifact_content`/`file_object_content` must be rejected. (IFC-2379)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 + US4 (Phase 2)**: Depends on Phase 1 completion — BLOCKS remaining stories
- **US2 (Phase 3)**: Depends on Phase 2 (uses InfrahubFilters + Jinja2Template wiring)
- **US3 (Phase 4)**: Depends on Phase 1 only (from_json/from_yaml need JinjaFilterError). Can start in parallel with Phase 2 if desired.
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **US4 + US1 (P1)**: Can start after Phase 1 — No dependencies on other stories. This is the MVP.
- **US2 (P2)**: Depends on US1 (reuses InfrahubFilters and Jinja2Template wiring from Phase 2)
- **US3 (P3)**: Depends on Phase 1 only for `from_json`/`from_yaml`. Chaining test (T011) depends on US1.

### Within Each Phase

- Tasks marked [P] can run in parallel (different files)
- Tests are included within each implementation task
- Core implementation before wiring/registration

### Parallel Opportunities

- T001 and T002 can run in parallel (different files: exceptions.py vs filters.py)
- T006 can run in parallel with T003/T004 (ObjectStore vs InfrahubFilters)
- T009 and T010 can run in parallel (from_json and from_yaml are independent)
- US3 Phase 4 (T009, T010) can start in parallel with Phase 2 after Phase 1 completes

---

## Parallel Example: Phase 1

```text
# Launch both foundational tasks together (different files):
Task T001: "JinjaFilterError in infrahub_sdk/template/exceptions.py"
Task T002: "ExecutionContext + FilterDefinition in infrahub_sdk/template/filters.py"
```

## Parallel Example: Phase 4

```text
# Launch both parsing filters together (same file but independent functions):
Task T009: "from_json filter in infrahub_sdk/template/infrahub_filters.py"
Task T010: "from_yaml filter in infrahub_sdk/template/infrahub_filters.py"
```

---

## Implementation Strategy

### MVP First (US1 + US4 Only)

1. Complete Phase 1: Foundational (T001, T002)
2. Complete Phase 2: US1 + US4 (T003, T004, T005)
3. **STOP and VALIDATE**: artifact_content renders, validation blocks in CORE, allows in WORKER
4. This alone delivers the primary value proposition

### Incremental Delivery

1. Phase 1 → Foundation ready
2. Phase 2 → artifact_content + security gate → **MVP deployed**
3. Phase 3 → file_object_content extends to file objects
4. Phase 4 → from_json/from_yaml enable structured composition
5. Phase 5 → Documentation + server integration
6. Each phase adds value without breaking previous phases

### Jira Task Mapping

| Task | Jira | Phase |
| ---- | ---- | ----- |
| T001 | IFC-2367 | 1 |
| T002 | IFC-2368 | 1 |
| T003 | IFC-2371 | 2 |
| T004 | IFC-2372 | 2 |
| T005 | IFC-2375 + IFC-2376 (partial) | 2 |
| T006 | IFC-2373 | 3 |
| T007 | IFC-2374 | 3 |
| T008 | IFC-2375 + IFC-2376 (partial) | 3 |
| T009 | IFC-2369 | 4 |
| T010 | IFC-2370 | 4 |
| T011 | IFC-2376 (partial) | 4 |
| T012-T013 | — | 5 |
| T014 | IFC-2377 | 5 |
| T015 | IFC-2378 | 5 |
| T016 | IFC-2379 | 5 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Tests are included in each implementation task (not separate)
- All error paths must produce actionable messages with filter name, cause, and remediation hint
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
