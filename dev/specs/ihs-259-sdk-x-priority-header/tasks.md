---
description: "Task list for SDK X-Priority request header (IHS-259)"
---

# Tasks: SDK `X-Priority` Request Header

**Input**: Design documents from `specs/ihs-259-sdk-x-priority-header/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the PRD (IHS-259 "Testing Decisions") and Success Criteria SC-001…SC-006 explicitly require unit + contract tests. Tests are first-class here.

**Organization**: Tasks are grouped by user story (from spec.md), in priority order. The MVP is User Story 1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US5 (setup / foundational / polish tasks have no story label)

## Path Conventions

Single-project Python library. Production code under `infrahub_sdk/`; tests under `tests/unit/sdk/`. Paths below are repository-relative (the `specs/` symlink resolves to `dev/specs/`).

## Prior art to mirror

- Header injection & per-request merge: `X-INFRAHUB-KEY` (`infrahub_sdk/client.py:217-218`) and `X-Infrahub-Tracker` (`client.py:1244-1246`, `1329-1333`, `2225-2226`, `2312-2313`).
- Enum pattern: `InfrahubClientMode(str, enum.Enum)` (`infrahub_sdk/constants.py:4`).
- Config enum field: `mode` / `transport` (`config.py:57`, `config.py:87`).
- Header-on-the-wire tests: `match_headers={...}` (`tests/unit/sdk/test_object_store.py:22-29`, `test_client.py:366+`); `BothClients` parity fixture (`tests/unit/sdk/conftest.py:33-45`).

---

## Phase 1: Setup

**Purpose**: Confirm the working environment before touching code.

- [X] T001 Ensure dev dependencies are installed and the baseline is green: run `uv sync --all-groups --all-extras` then `uv run pytest tests/unit/sdk/test_config.py tests/unit/sdk/test_client.py -q` to confirm a clean starting point. (Done: 107 passed on baseline.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `Priority` enum and `Config.priority` field are prerequisites for every user story. MUST complete before Phase 3+.

- [X] T002 Add `class Priority(str, enum.Enum)` with members `HIGH = "high"`, `NORMAL = "normal"`, `LOW = "low"` and a case-insensitive `_missing_` classmethod (returns the member matching `value.lower()`, else `None`) to `infrahub_sdk/constants.py` (mirror `InfrahubClientMode`). Add module docstring/type hints per repo style.
- [X] T003 [P] Export `Priority` from the SDK public namespace: add it to `infrahub_sdk/__init__.py` imports and `__all__` (alongside other public enums), per contracts/priority-api.md.
- [X] T004 Add `priority: Priority | None = Field(default=None, description="Default request priority emitted as the X-Priority header on every request; one of high|normal|low (case-insensitive). When unset, no header is sent.")` to `ConfigBase` in `infrahub_sdk/config.py`; import `Priority` from `.constants`. Confirm the field auto-binds to `INFRAHUB_PRIORITY` (no custom source needed) and is carried by `Config.clone()` (it iterates `model_fields`, so no change to `clone()` required — verify only).

**Checkpoint**: `Priority` importable from `infrahub_sdk`; `Config(priority=...)` accepts enum/string; the SDK still imports and existing tests still pass.

---

## Phase 3: User Story 1 - Client-wide default priority (Priority: P1) 🎯 MVP

**Goal**: A client built with a default priority emits `X-Priority: <value>` on every request across all transports, with no call-site changes.

**Independent test**: Construct a client with `priority=Priority.LOW`; issue one GraphQL, one multipart upload, and one blob `_get`/`_post`; assert each outgoing request carries `X-Priority: low`.

### Implementation

- [ ] T005 [US1] In `BaseClient.__init__` (`infrahub_sdk/client.py`, next to the `X-INFRAHUB-KEY` block ~line 217-218), inject the default once: `if self.config.priority is not None: self.headers["X-Priority"] = self.config.priority.value`. This single edit covers async and sync (both subclass `BaseClient`) and, because every transport re-merges `self.headers`, rides GraphQL, multipart, and raw blob transports automatically.

### Tests

- [ ] T006 [P] [US1] Add `tests/unit/sdk/test_priority.py`: assert a `priority=Priority.LOW` client emits `X-Priority: low` on a GraphQL query and a mutation, for both clients (`match_headers={"X-Priority": "low"}`, parametrized over the `BothClients` fixture). (SC-001, FR-003)
- [ ] T007 [P] [US1] In `tests/unit/sdk/test_object_store.py` (or `test_priority.py`), assert a `priority=Priority.LOW` client emits `X-Priority: low` on a blob download (`_get_streaming`) and upload (`_post`/object-store), both clients. (SC-001, SC-006 blob)
- [ ] T008 [P] [US1] Add a multipart-upload test: a `priority=Priority.LOW` client emits `X-Priority: low` on `_execute_graphql_with_file`, both clients (confirm the header survives the `content-type` pop). (SC-001, FR-003)
- [ ] T009 [P] [US1] Add a batch-mode test: a `priority=Priority.LOW` client issues a batched operation and every batched request carries `X-Priority: low`. (SC-006 batch)
- [ ] T010 [P] [US1] Add a test that a `priority=Priority.NORMAL` client emits `X-Priority: normal` on requests (an explicitly configured default is always emitted, not omitted), both clients. (US1 acceptance #4, FR-006)

**Checkpoint**: US1 fully testable and green independently — this is a shippable MVP.

---

## Phase 4: User Story 3 - Zero behaviour change when unconfigured (Priority: P1)

**Goal**: A client with no priority configured (and no per-request arg) emits no `X-Priority` header anywhere — identical to the pre-feature SDK.

**Independent test**: Construct a client with no `priority`; issue requests across transports; assert no `X-Priority` header is present.

**Note**: The conditional in T005 already implements the omit path; this phase locks it with tests. Depends on T005.

### Tests

- [ ] T011 [P] [US3] In `tests/unit/sdk/test_priority.py`, assert an unconfigured client emits **no** `X-Priority` header across GraphQL, multipart, and blob transports — capture the request via `httpx_mock.get_requests()` and assert `"x-priority" not in request.headers`, both clients. (SC-002, FR-004)
- [ ] T012 [P] [US3] Assert that with no priority configured, no per-request arg, the SDK-set outgoing headers are unchanged versus baseline (only `X-Priority` absence matters; do not assert on transport-injected headers like host/user-agent). (SC-002)

**Checkpoint**: Backwards compatibility proven for both clients.

---

## Phase 5: User Story 2 - Per-request override (Priority: P2)

**Goal**: A `priority=` argument on the covered public methods overrides the client default for exactly one request, resolving as `per_request if per_request is not None else client_default`.

**Independent test**: On a client with no default, call a covered method with `priority=Priority.HIGH` (asserts `X-Priority: high`), then call it again with no arg (asserts no header).

### Implementation

- [ ] T013 [US2] Add `priority: Priority | None = None` to async `execute_graphql` (`client.py:1201`) and apply the override after the existing `headers = copy.copy(self.headers or {})` + tracker block: `if priority is not None: headers["X-Priority"] = priority.value`. (FR-005, FR-006)
- [ ] T014 [US2] Add `priority: Priority | None = None` to async `_execute_graphql_with_file` (`client.py:1290`); apply the override **after** the copy and the `content-type` pop so it is not lost. (FR-005, FR-006, critique E3)
- [ ] T015 [US2] Mirror T013–T014 on the sync client: `execute_graphql` (`client.py:2181`) and `_execute_graphql_with_file` (`client.py:2270`). (FR-008)
- [ ] T016 [US2] Thread `priority` through the client high-level methods so they forward it to the execute funnels: async `get` (`client.py:442`), `all`→`filters` (`client.py:905`/`1131`), `create` (`client.py:400`); ensure the pagination loop in `filters` forwards `priority` on **every** page request. (FR-005, critique E2)
- [ ] T017 [US2] Thread `priority` through the diff methods: `create_diff` (`client.py:1695`), `get_diff_summary` (`client.py:1724`), `get_diff_tree` (`client.py:1763`), forwarding to `execute_graphql`. (FR-005)
- [ ] T018 [US2] Mirror T016–T017 on the sync client (`get` `client.py:2975`, `all` `client.py:2639`/`2907`, `create` `client.py:2137`, `create_diff` `client.py:3266`, `get_diff_summary`/`get_diff_tree`). (FR-008)
- [ ] T019 [US2] Add `priority: Priority | None = None` to async node methods and forward to the client execute calls: `save` (`node/node.py:1241`), `create` (`node/node.py:1602`), `update` (`node/node.py:1681`), `delete` (`node/node.py:1214`). (FR-005)
- [ ] T020 [US2] Mirror T019 on the sync node (`InfrahubNodeSync`: `delete` `node/node.py:2402`, `save` `node/node.py:2429`, plus `create`/`update`). (FR-008)

### Tests

- [ ] T021 [P] [US2] Test: no-default client + `priority=Priority.HIGH` on `execute_graphql` emits `X-Priority: high`; a following un-annotated call emits no header (no leak). Both clients. (SC-003, US2 acceptance #1/#2)
- [ ] T022 [P] [US2] Test: `priority=Priority.LOW` default client + per-request `priority=Priority.HIGH` emits `X-Priority: high` for that call, and the next un-annotated call reverts to `X-Priority: low`. Both clients. (SC-003, US2 acceptance #3)
- [ ] T023 [P] [US2] Test: `priority=Priority.LOW` default client + per-request `priority=Priority.NORMAL` emits `X-Priority: normal` (explicit step-up wins). Both clients. (spec Edge Cases, SC-003)
- [ ] T024 [P] [US2] Test the override on the covered surfaces: `get`, `all` (multi-page — assert every page request carries the override), `create`, `save`, a diff method, and `_execute_graphql_with_file`. Both clients. (FR-005, critique E2/E3)

**Checkpoint**: Override works and resolves correctly on every covered surface, both clients.

---

## Phase 6: User Story 4 - Invalid configured priority rejected (Priority: P2)

**Goal**: An invalid/unknown configured priority fails at config load; valid strings in any case are accepted.

**Independent test**: `Config(priority="lowe")` raises; `Config(priority="LOW").priority is Priority.LOW`.

**Note**: Validation comes for free from the enum + `_missing_` (T002/T004); this phase locks it with tests.

### Tests

- [ ] T025 [P] [US4] In `tests/unit/sdk/test_config.py`, assert `Config(address="http://localhost:8000", priority="lowe")` raises `pydantic.ValidationError` (use `pytest.raises(..., match=...)`); assert no request is issued. (SC-004, FR-007)
- [ ] T026 [P] [US4] Assert case-insensitive acceptance: `Config(priority="LOW")`, `Config(priority="Low")`, `Config(priority="low")`, and `Config(priority=Priority.LOW)` all yield `Priority.LOW`; likewise for HIGH/NORMAL. Include the env-var path `INFRAHUB_PRIORITY=LOW` via `monkeypatch`. (SC-004, FR-002)
- [ ] T027 [P] [US4] Assert `Config()` default → `priority is None` (no default, header omitted). (FR-004)

**Checkpoint**: Misconfiguration fails loudly; valid config in any case is accepted.

---

## Phase 7: User Story 5 - Async / sync parity (Priority: P1)

**Goal**: Every aspect behaves identically on `InfrahubClient` and `InfrahubClientSync`.

**Independent test**: The same assertion suite runs against both clients with identical outcomes.

- [ ] T028 [US5] Audit T006–T012 and T021–T024 to confirm every wire/resolution test is parametrized over the `BothClients` fixture (`["standard","sync"]`); add parametrization to any that isn't. (SC-005, FR-008)
- [ ] T029 [P] [US5] Add a focused parity test asserting the resolution truth table (data-model.md) produces identical emitted headers for both clients across the default × override combinations. (SC-005)

**Checkpoint**: Parity is explicit and enforced, not incidental.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Docs, quality gates, and release hygiene.

- [ ] T030 Add docstrings to the new `Priority` enum, the `Config.priority` field, and the `priority` kwarg on the covered public methods (drives generated docs).
- [ ] T031 Run `uv run invoke docs-generate`, then `uv run invoke docs-validate`; commit the regenerated docs (new `Config.priority` field). (Governance gate: docs regeneration)
- [ ] T032 [P] Add a changelog fragment under `changelog/` (mirror the existing fragment style, e.g. an `.added.md` for the new `Priority`/`Config.priority`/`priority=` surface referencing IHS-259 / #1151).
- [ ] T033 Run `uv run invoke format lint-code` (ruff, ty, mypy) and fix any findings; confirm type hints on all new/changed signatures.
- [ ] T034 Run the full `uv run pytest tests/unit/` suite and confirm green (including all new priority tests for both clients).
- [ ] T035 Validate against quickstart.md: run the mapped validation scenarios and confirm SC-001…SC-006 are all covered.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational: T002–T004)** must complete first; they block everything.
- **Phase 3 (US1)** depends on T004 (config field) + T005 (base injection). This is the MVP.
- **Phase 4 (US3)** depends on T005 (shares the conditional-injection code). Can be developed right after US1.
- **Phase 5 (US2)** depends on Foundational (enum) and is independent of US1's base injection for its core (works on a no-default client), but its "override beats default" tests (T022–T023) depend on T005.
- **Phase 6 (US4)** depends only on Foundational (T002/T004).
- **Phase 7 (US5)** depends on the tests from US1–US4 existing (it audits/extends them).
- **Phase 8 (Polish)** last.

### Story independence

- US1, US3, US4 are each independently testable after Foundational.
- US2 is independently testable on a no-default client after Foundational; full override-vs-default coverage wants T005.
- US5 is a cross-cutting invariant realized by parametrizing the other stories' tests.

### Parallelization

- **Foundational**: T003 [P] can run alongside T002/T004 once `Priority` exists.
- **Within US1**: T006–T010 are all [P] (independent test files/cases) once T005 lands.
- **Within US2**: implementation T013–T020 touch overlapping regions of `client.py`/`node.py` (mostly sequential per file); tests T021–T024 are [P].
- **Within US4**: T025–T027 are [P].
- **Polish**: T032 [P]; T031/T033/T034 are sequential gates.

## Implementation Strategy

1. **MVP first**: Phases 1–3 (Setup → Foundational → US1). Ship a client-wide default that rides every transport.
2. **Lock safety**: Phase 4 (US3) — prove zero behaviour change when unconfigured.
3. **Add control**: Phase 5 (US2) — per-request override.
4. **Harden**: Phases 6–7 (US4 validation, US5 parity).
5. **Finish**: Phase 8 — docs, changelog, quality gates.

## Task summary

- **Total tasks**: 35
- **By story**: Foundational 3 (T002–T004) + Setup 1 + US1 6 (T005–T010) + US3 2 (T011–T012) + US2 12 (T013–T024) + US4 3 (T025–T027) + US5 2 (T028–T029) + Polish 6 (T030–T035)
- **MVP scope**: T001–T010 (Setup + Foundational + US1)
