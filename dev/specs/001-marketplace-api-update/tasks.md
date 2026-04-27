---
description: "Task list for the Marketplace Download Command Update"
---

# Tasks: Marketplace Download Command Update

**Input**: Design documents from `specs/001-marketplace-api-update/`
**Prerequisites**: plan.md, spec.md, research.md, contracts/marketplace-api.md, quickstart.md

**Tests**: TDD is on — each user story leads with unit tests using `pytest` + `pytest-httpx`, following the pattern already in `tests/unit/ctl/test_marketplace_app.py`.

**Organization**: Tasks are grouped by user story. Nearly all edits concentrate in two files (`infrahub_sdk/ctl/marketplace.py` and `tests/unit/ctl/test_marketplace_app.py`), so most tasks run sequentially; `[P]` appears where a task lands in a distinct file from its siblings.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps task to its user story (US1, US2, US3)
- Every task names an exact file path

## Path Conventions

Single project: repository root contains `infrahub_sdk/` and `tests/`. All paths below are repo-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No project initialization required — `infrahub_sdk/ctl/marketplace.py` and its test file already exist.

- [ ] T001 Confirm baseline: run `uv run pytest tests/unit/ctl/test_marketplace_app.py -v` and record a green baseline before any changes to `infrahub_sdk/ctl/marketplace.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reusable helpers that every user story needs. Must land before US1 because the auto-detect path depends on them.

**⚠️ CRITICAL**: No user-story implementation tasks (T006 onward) may start until this phase is complete.

- [ ] T002 Introduce an internal enum/literal `MarketplaceItemType` (values `"schema"` | `"collection"`) in `infrahub_sdk/ctl/marketplace.py` to be returned by the new detection helper.
- [ ] T003 Add a private `_classify_http_error(exc_or_response) -> tuple[ErrorClass, str]` helper in `infrahub_sdk/ctl/marketplace.py` implementing the four-class taxonomy from `research.md` R-4 (invalid-input, not-found, version-not-found, network). Include a matching `ErrorClass` enum/literal.
- [ ] T004 Centralize console error emission in `infrahub_sdk/ctl/marketplace.py` via a `_fail(error_class, message)` helper that prints the coloured error line and raises `typer.Exit(1)` for input/not-found classes and `typer.Exit(2)` for network class (per `research.md` R-4 exit-code table).
- [ ] T005 Extend `_parse_identifier` in `infrahub_sdk/ctl/marketplace.py` to route its current inline error through the new `_fail("invalid-input", ...)` helper, preserving existing behaviour for backwards compat.

**Checkpoint**: Helpers in place; user-story phases can now begin.

---

## Phase 3: User Story 1 — Auto-detect schema vs. collection (Priority: P1) 🎯 MVP

**Goal**: A single `infrahubctl marketplace download <namespace>/<name>` command resolves to the correct item type without the user passing `--collection`, and prints the resolved type in success output.

**Independent Test**: Mock one schema endpoint and one collection endpoint (as in `tests/unit/ctl/test_marketplace_app.py`). Run the download twice with no `--collection` flag — once against each identifier. Both succeed, files land at the expected paths, and the output names the resolved type.

### Tests for User Story 1 (write first, ensure they fail)

- [ ] T006 [US1] Add `test_autodetect_schema` in `tests/unit/ctl/test_marketplace_app.py`: only the schema endpoint returns 200; collection endpoint returns 404. Assert exit 0, schema file written, output mentions "schema".
- [ ] T007 [US1] Add `test_autodetect_collection` in `tests/unit/ctl/test_marketplace_app.py`: only the collection endpoint returns 200; schema endpoint returns 404. Assert exit 0, collection files written, output mentions "collection".
- [ ] T008 [US1] Add `test_autodetect_collision_schema_wins` in `tests/unit/ctl/test_marketplace_app.py`: both endpoints return 200 for the same `namespace/name`. Assert resolved as schema, output prints both the resolved type and a hint that `--collection` can force the other path.
- [ ] T009 [US1] Add `test_autodetect_not_found` in `tests/unit/ctl/test_marketplace_app.py`: both endpoints return 404. Assert exit 1, error class "not found", message names the identifier and marketplace host.
- [ ] T010 [US1] Add `test_autodetect_network_error` in `tests/unit/ctl/test_marketplace_app.py`: either probe raises `httpx.ConnectError`. Assert exit 2, error class "network", message names the base URL.
- [ ] T011 [US1] Add `test_collection_flag_overrides_autodetect` in `tests/unit/ctl/test_marketplace_app.py`: user passes `--collection`; assert the schema endpoint is NOT probed (use `httpx_mock` to fail the test if it is called) and the collection endpoint is used directly.

### Implementation for User Story 1

- [ ] T012 [US1] Add `async def _detect_item_type(client, base_url, namespace, name) -> MarketplaceItemType` in `infrahub_sdk/ctl/marketplace.py` that issues schema and collection probes in parallel via `asyncio.gather(..., return_exceptions=True)`, applies "schema wins" precedence on 200-200, raises a typed network error if both probes raise transport exceptions, and raises a typed not-found error if both return 404.
- [ ] T013 [US1] Update `download()` in `infrahub_sdk/ctl/marketplace.py`: when `collection=False` and the user did NOT explicitly pass `--collection` (i.e. default), call `_detect_item_type` first, then dispatch to `_download_schema` or `_download_collection` based on the result.
- [ ] T014 [US1] Modify `_download_schema` and `_download_collection` in `infrahub_sdk/ctl/marketplace.py` to print the resolved item type on their first success line (e.g. `Downloaded schema acme/network-base v1.2.0 -> ...` and `Downloaded collection acme/starter-pack: ...`), per FR-010.
- [ ] T015 [US1] Make the `collection: bool` option explicit-only: detect whether the user actually typed `--collection` by using `typer.Option(None, ...)` default and treating `None` as "auto", `True` as "force collection", `False` as "force schema" (so T013 can branch correctly without mistaking a default `False` for an explicit override).
- [ ] T016 [US1] Route the existing 404 handling in `_download_schema` and `_download_collection` in `infrahub_sdk/ctl/marketplace.py` through `_fail("not-found", ...)`.
- [ ] T017 [US1] Add network-error handling (`httpx.ConnectError`, `httpx.TimeoutException`, 5xx) wrapping the `async with httpx.AsyncClient...` block in `infrahub_sdk/ctl/marketplace.py`'s `download()` and route through `_fail("network", ...)`.

**Checkpoint**: Tests T006–T011 all pass. Running `infrahubctl marketplace download acme/starter-pack` (collection) and `infrahubctl marketplace download acme/network-base` (schema) both succeed without `--collection`, and the output names the resolved type. MVP scope.

---

## Phase 4: User Story 2 — Pin schema version (Priority: P2)

**Goal**: `--version <semver>` pins a schema download; when the version is unpublished, the error clearly distinguishes "version missing" from "schema missing".

**Independent Test**: Publish at least two versions of the same schema (mock) and confirm `--version <older>` writes the older payload. Separately, pass an unpublished `--version` and confirm the CLI emits the "version not found" error class with a hint to drop `--version`.

### Tests for User Story 2

- [ ] T018 [P] [US2] Add `test_version_not_found` in `tests/unit/ctl/test_marketplace_app.py`: unversioned schema probe returns 200, versioned schema probe returns 404. Assert exit 1, error class "version not found", message names the version and suggests running without `--version`.
- [ ] T019 [P] [US2] Extend `test_download_schema_specific_version` in `tests/unit/ctl/test_marketplace_app.py` to assert the success output still echoes the pinned version unchanged under auto-detect.

### Implementation for User Story 2

- [ ] T020 [US2] In `infrahub_sdk/ctl/marketplace.py` `_download_schema`, when `version` is provided and the versioned request returns 404, first retry an unversioned HEAD/GET against the same identifier to decide between "schema not found" and "version not found"; route through `_fail` with the appropriate class.
- [ ] T021 [US2] Confirm that the existing "`--version` is ignored when downloading a collection" warning (currently at `marketplace.py:146-147`) still fires on the auto-detect path — i.e. when the user passed `--version` and the detected type is `collection`, the warning is printed before falling through to `_download_collection`. Add/adjust wiring in `download()` in `infrahub_sdk/ctl/marketplace.py` as needed.

**Checkpoint**: US1 still passes; T018 and T019 pass; `infrahubctl marketplace download acme/network-base --version 9.9.9` prints the version-not-found message and exits 1.

---

## Phase 5: User Story 3 — Custom output directory (Priority: P2)

**Goal**: `--output-dir` redirects all output with a working default of `./schemas`; filesystem failures are surfaced cleanly.

**Independent Test**: Run the download with `--output-dir ./custom/does-not-exist-yet` — files land under that path and only that path; running again with `--output-dir` pointing to a non-writable path fails with a filesystem-class error that names the path.

### Tests for User Story 3

- [ ] T022 [P] [US3] Add `test_output_dir_creates_nested_missing_parents` in `tests/unit/ctl/test_marketplace_app.py`: supply a multi-level `--output-dir` under `tmp_path` that does not yet exist. Assert directory tree is created and files land under it.
- [ ] T023 [P] [US3] Add `test_output_dir_default_is_schemas` in `tests/unit/ctl/test_marketplace_app.py`: run inside a `tmp_path`-rooted cwd (via `monkeypatch.chdir(tmp_path)`), omit `--output-dir`, assert the file appears under `tmp_path / "schemas"`.
- [ ] T024 [P] [US3] Add `test_output_dir_permission_error` in `tests/unit/ctl/test_marketplace_app.py`: supply an unwritable `--output-dir` (e.g. `monkeypatch` `Path.mkdir` to raise `PermissionError`). Assert exit 1 and an error message naming the target path, with no partial writes elsewhere.

### Implementation for User Story 3

- [ ] T025 [US3] Wrap directory creation in `_download_schema` and `_download_collection` in `infrahub_sdk/ctl/marketplace.py` with a filesystem-error branch that routes through `_fail("invalid-input", ...)` with a message naming the offending path. No code change should be required for the happy path — tests T022 and T023 should pass on the existing implementation once auto-detect (US1) is wired.

**Checkpoint**: US1 and US2 still pass; T022–T024 pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalise help text, docs, and verification gates.

- [ ] T026 Update the `download` command's docstring and flag helps in `infrahub_sdk/ctl/marketplace.py` to reflect auto-detection (e.g. "By default, the CLI automatically determines whether `namespace/name` is a schema or a collection. Pass `--collection` to force the collection path.").
- [ ] T027 [P] If the docs site documents the marketplace CLI, update the relevant page under `docs/` to describe auto-detect, the `--version` error behaviour, and the `--output-dir` default. Run `uv run invoke docs-generate` afterward. (Skip this task with a brief note if no such doc page exists.)
- [ ] T028 Run `uv run invoke format lint-code` and fix any issues it reports in `infrahub_sdk/ctl/marketplace.py` and `tests/unit/ctl/test_marketplace_app.py`.
- [ ] T029 Walk through every manual command block in `specs/001-marketplace-api-update/quickstart.md` against the public marketplace or a local instance; fix any mismatch between quickstart output shapes and actual output.
- [ ] T030 Run the full unit suite `uv run pytest tests/unit/` and confirm green before requesting review.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** → starts immediately; only gates recording the baseline.
- **Phase 2 (Foundational)** → depends on T001; blocks all user-story phases.
- **Phase 3 (US1)** → depends on Phase 2 completion.
- **Phase 4 (US2)** → depends on Phase 3 (the error helpers and auto-detect plumbing from US1 are reused by US2's version-distinction logic).
- **Phase 5 (US3)** → depends on Phase 2 only; can run in parallel with Phase 4 if staffed accordingly (US3's tests operate on the same file as US1/US2 but touch distinct code paths in `marketplace.py`).
- **Phase 6 (Polish)** → depends on all user-story phases that are in scope for the cut being made.

### Within Each User Story

- Tests are written first (T006–T011, T018–T019, T022–T024) and MUST fail before their implementation counterparts.
- Foundational helpers (T002–T005) before they are used.
- T012 (`_detect_item_type`) before T013 (`download()` wiring).
- T015 (option default change) before or together with T013 to avoid a transient broken state.

### Parallel Opportunities

- Within Phase 3, T006–T011 touch the same file (`tests/unit/ctl/test_marketplace_app.py`), so they run sequentially unless the team splits the file (not recommended). No `[P]` markers in US1.
- T018 and T019 (Phase 4 tests) and T022–T024 (Phase 5 tests) are marked `[P]` because they target independent test functions; they can be drafted in parallel and committed in one batch.
- Phase 5 implementation (T025) and Phase 4 implementation (T020–T021) operate on different code paths within the same module and should be merged sequentially to keep the diff clean; do not flag as `[P]`.

---

## Parallel Example: User Story 2

```bash
# Developers A and B can draft these tests simultaneously (different test functions):
Task: "Add test_version_not_found in tests/unit/ctl/test_marketplace_app.py"
Task: "Extend test_download_schema_specific_version in tests/unit/ctl/test_marketplace_app.py"
```

Implementation then merges into `_download_schema` / `download()` in `infrahub_sdk/ctl/marketplace.py` sequentially (T020 → T021).

---

## Implementation Strategy

### MVP scope (ship US1 alone)

1. Complete Phase 1 (T001).
2. Complete Phase 2 (T002–T005).
3. Complete Phase 3 (T006–T017).
4. **STOP and VALIDATE**: `uv run pytest tests/unit/ctl/test_marketplace_app.py -v` green; spot-check against the public marketplace per `quickstart.md` Scenarios 1–2.
5. Ship MVP. This alone satisfies the user's stated top ask: "auto-detect if namespace is a collection or a schema".

### Incremental delivery

- MVP (US1) → ship → gather feedback → add US2 (version error taxonomy) → ship → add US3 (output-dir polish/tests) → ship.
- Each increment keeps earlier stories green.

### Parallel team strategy

With two or more developers after Phase 2:

- Dev A: Phase 3 (US1) — critical path.
- Dev B: Phase 5 (US3) — independent code paths; merges after Dev A lands the option-default change (T015) to avoid stomping on the `collection` signature.
- Either dev then picks up Phase 4 (US2) once Phase 3 merges.

---

## Notes

- [P] tasks = different files or distinct test functions, no dependencies on incomplete tasks.
- Almost all implementation lives in `infrahub_sdk/ctl/marketplace.py` — watch for merge conflicts when parallelising.
- Verify new tests fail before their paired implementation tasks.
- Commit after each task or small group (e.g. T002–T005 together; each test in US1 with its implementation task).
- The existing `Marketplace` commit (`5452df9`) already satisfies FR-001/002/004/006/007/009/010/011; the tasks above close the gaps on FR-003, FR-005 (auto-detect path), FR-008, and FR-012.
