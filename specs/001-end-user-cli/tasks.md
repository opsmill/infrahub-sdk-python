# Tasks: End-User CLI (`infrahub` command)

**Input**: Design documents from `/specs/001-end-user-cli/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED per FR-015. Unit tests for all public functions, integration tests for Infrahub server interactions.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `infrahub_sdk/ctl/` (extends existing CLI package)
- **Unit tests**: `tests/unit/ctl/`
- **Integration tests**: `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `infrahub` entry point and package structure

- [x] T001 Add `infrahub` entry point to `[project.scripts]` in pyproject.toml pointing to `infrahub_sdk.ctl.enduser_cli:app`
- [x] T002 Create CLI entry point module in infrahub_sdk/ctl/enduser_cli.py with AsyncTyper app and error-handling wrapper (matching infrahub_sdk/ctl/cli.py pattern)
- [x] T003 [P] Create commands package with infrahub_sdk/ctl/commands/\_\_init\_\_.py
- [x] T004 [P] Create formatters package with infrahub_sdk/ctl/formatters/\_\_init\_\_.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure reused by ALL user story commands

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Implement `--set` flag parser (parse `key=value` strings into dict) in infrahub_sdk/ctl/parsers.py
- [x] T006 Implement `--filter` flag parser (parse `attr__value=x` strings into kwargs dict) in infrahub_sdk/ctl/parsers.py
- [x] T007 Implement output format auto-detection (TTY → table, piped → json) and `OutputFormat` enum in infrahub_sdk/ctl/formatters/\_\_init\_\_.py
- [x] T008 [P] Implement base formatter protocol with `format_list()` and `format_detail()` methods in infrahub_sdk/ctl/formatters/base.py
- [x] T009 [P] Implement Rich table formatter (list view: attribute + relationship columns with display names; detail view: key-value pairs) in infrahub_sdk/ctl/formatters/table.py
- [x] T010 [P] Implement JSON formatter (list and detail mode) in infrahub_sdk/ctl/formatters/json.py
- [x] T011 [P] Implement CSV formatter (list mode; detail mode falls back to key-value) in infrahub_sdk/ctl/formatters/csv.py
- [x] T012 [P] Implement Infrahub Object YAML formatter (serialize nodes to apiVersion/kind/spec.kind/spec.data structure, round-trippable with ObjectFile) in infrahub_sdk/ctl/formatters/yaml.py
- [x] T013 Create command registration module in infrahub_sdk/ctl/enduser_commands.py (register all command groups on the app)
- [x] T014 [P] Write unit tests for set/filter parsers in tests/unit/ctl/test_parsers.py
- [x] T015 [P] Write unit tests for table formatter in tests/unit/ctl/formatters/test_table.py
- [x] T016 [P] Write unit tests for JSON formatter in tests/unit/ctl/formatters/test_json.py
- [x] T017 [P] Write unit tests for CSV formatter in tests/unit/ctl/formatters/test_csv.py
- [x] T018 [P] Write unit tests for YAML formatter (verify round-trip structure matches InfrahubObjectFileData) in tests/unit/ctl/formatters/test_yaml.py

**Checkpoint**: Foundation ready - all formatters, parsers, and app skeleton in place. User story commands can now be implemented.

---

## Phase 3: User Story 1 - Query Data (Priority: P1) MVP

**Goal**: Users can retrieve data from Infrahub with `infrahub get <kind>` (list) and `infrahub get <kind> <identifier>` (detail), with filtering, pagination, and all output formats.

**Independent Test**: Run `infrahub get <any-kind>` against an Infrahub instance and verify formatted output. Test all four output formats. Test `--filter`, `--limit`, `--offset`, `--branch`.

### Tests for User Story 1

- [x] T019 [P] [US1] Write unit tests for get command (list mode, detail mode, invalid kind error, filter passthrough, pagination args, output format selection) in tests/unit/ctl/commands/test_get.py
- [x] T020 [P] [US1] Write integration test for get command (query real data, verify table/json/yaml/csv output) in tests/integration/test_enduser_cli.py

### Implementation for User Story 1

- [x] T021 [US1] Implement `infrahub get` command with list mode (`client.filters()` with kwargs from --filter, --limit, --offset, --branch) and detail mode (`client.get()` with identifier) in infrahub_sdk/ctl/commands/get.py
- [x] T022 [US1] Wire get command into enduser_commands.py and verify `infrahub get` works end-to-end
- [x] T023 [US1] Add error handling for invalid kind (suggest similar kinds from schema), not-found identifier, and connection failures in infrahub_sdk/ctl/commands/get.py

**Checkpoint**: `infrahub get` fully functional with all output formats, filtering, pagination, detail view. MVP complete.

---

## Phase 4: User Story 2 - Create Objects (Priority: P2)

**Goal**: Users can create new objects with `infrahub create <kind> --set key=value` or `infrahub create <kind> --file objects.yaml`.

**Independent Test**: Create an object via `--set` flags, then verify it exists with `infrahub get`. Create objects from a YAML file and verify batch results.

### Tests for User Story 2

- [x] T024 [P] [US2] Write unit tests for create command (inline --set, file input, mutual exclusivity of --set/--file, validation errors, batch summary) in tests/unit/ctl/commands/test_create.py
- [x] T025 [P] [US2] Write integration test for create command (create via --set, create via --file, verify with get) in tests/integration/test_enduser_cli.py

### Implementation for User Story 2

- [x] T026 [US2] Implement `infrahub create` command with inline mode (`client.create()` + `node.save()` using parsed --set data) and file mode (load via ObjectFile, validate, process) in infrahub_sdk/ctl/commands/create.py
- [x] T027 [US2] Wire create command into enduser_commands.py
- [x] T028 [US2] Add validation error handling (invalid fields → show valid attribute/relationship names from schema) and batch result summary in infrahub_sdk/ctl/commands/create.py

**Checkpoint**: `infrahub create` works with both inline and file input. Users can create and then query back objects.

---

## Phase 5: User Story 3 - Update Objects (Priority: P3)

**Goal**: Users can update existing objects with `infrahub update <kind> <identifier> --set key=value` or `--file`.

**Independent Test**: Update an attribute on an existing object, then query it to verify the change. Show old vs new values in confirmation.

### Tests for User Story 3

- [x] T029 [P] [US3] Write unit tests for update command (inline --set, file input, not-found error, old/new value display) in tests/unit/ctl/commands/test_update.py
- [x] T030 [P] [US3] Write integration test for update command (update attribute, verify change persists) in tests/integration/test_enduser_cli.py

### Implementation for User Story 3

- [x] T031 [US3] Implement `infrahub update` command (`client.get()` to fetch node, apply --set changes to attributes/relationships, `node.save()`, display old → new values) in infrahub_sdk/ctl/commands/update.py
- [x] T032 [US3] Wire update command into enduser_commands.py
- [x] T033 [US3] Add file-based update mode and not-found error handling in infrahub_sdk/ctl/commands/update.py

**Checkpoint**: `infrahub update` works. Full create → query → update → query cycle verified.

---

## Phase 6: User Story 4 - Delete Objects (Priority: P4)

**Goal**: Users can delete objects with `infrahub delete <kind> <identifier>` with confirmation prompt and `--yes` bypass.

**Independent Test**: Create an object, delete it (with and without --yes), verify it no longer appears in query results.

### Tests for User Story 4

- [x] T034 [P] [US4] Write unit tests for delete command (confirmation prompt, --yes bypass, not-found, dependency conflict error) in tests/unit/ctl/commands/test_delete.py
- [x] T035 [P] [US4] Write integration test for delete command (create, delete, verify gone) in tests/integration/test_enduser_cli.py

### Implementation for User Story 4

- [x] T036 [US4] Implement `infrahub delete` command (`client.get()` to fetch, confirmation prompt via typer.confirm(), `node.delete()`, --yes flag to skip) in infrahub_sdk/ctl/commands/delete.py
- [x] T037 [US4] Wire delete command into enduser_commands.py
- [x] T038 [US4] Add dependency conflict error handling (catch server error, display dependent objects) in infrahub_sdk/ctl/commands/delete.py

**Checkpoint**: Full CRUD cycle complete. All data operations functional.

---

## Phase 7: User Story 5 - Schema Discovery (Priority: P5)

**Goal**: Users can explore the data model with `infrahub schema list` and `infrahub schema show <kind>`.

**Independent Test**: List all schema kinds, verify output matches actual schema. Show a specific kind's attributes and relationships.

### Tests for User Story 5

- [x] T039 [P] [US5] Write unit tests for schema list and schema show commands (list with filter, show with valid/invalid kind, attribute/relationship table output) in tests/unit/ctl/commands/test_schema.py
- [x] T040 [P] [US5] Write integration test for schema commands (list against real instance, show known kind) in tests/integration/test_enduser_cli.py

### Implementation for User Story 5

- [x] T041 [US5] Implement `infrahub schema list` command (`client.schema.all()`, filter by substring, display table with Namespace/Name/Kind/Description columns) in infrahub_sdk/ctl/commands/schema.py
- [x] T042 [US5] Implement `infrahub schema show <kind>` command (`client.schema.get()`, display metadata + attributes table + relationships table) in infrahub_sdk/ctl/commands/schema.py
- [x] T043 [US5] Wire schema command group into enduser_commands.py

**Checkpoint**: All 5 user stories complete. Full CLI feature set available.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, documentation, and validation

- [x] T044 Run `uv run invoke format` and `uv run invoke lint-code` across all new files
- [x] T045 Run `uv run pytest tests/unit/ctl/` to verify all unit tests pass
- [x] T046 Run `uv run invoke docs-generate` and `uv run invoke docs-validate` to update CLI documentation
- [x] T047 Verify type checking passes: `uv run invoke lint` (includes mypy and ty)
- [x] T048 Run quickstart.md validation: manually execute the quickstart steps against a test instance
- [x] T049 [P] Add Google-style docstrings to all new modules, classes, and public functions if not already present

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T004) - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (get) has no dependencies on other stories
  - US2 (create) has no dependencies on other stories (reuses parsers from Phase 2)
  - US3 (update) has no dependencies on other stories
  - US4 (delete) has no dependencies on other stories
  - US5 (schema) has no dependencies on other stories
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2. No cross-story dependencies.
- **US2 (P2)**: Can start after Phase 2. Independent of US1 (uses same parsers/formatters).
- **US3 (P3)**: Can start after Phase 2. Independent of US1/US2.
- **US4 (P4)**: Can start after Phase 2. Independent of US1/US2/US3.
- **US5 (P5)**: Can start after Phase 2. Independent of all other stories.

### Within Each User Story

- Unit tests written first (marked [P] where independent)
- Command implementation after tests exist
- Integration into enduser_commands.py after command works
- Error handling as final step in each story

### Parallel Opportunities

- T003, T004: Package init files can be created in parallel
- T008-T012: All formatters can be implemented in parallel (different files)
- T014-T018: All foundational unit tests can run in parallel
- T019, T020: US1 tests can be written in parallel
- T024, T025: US2 tests can be written in parallel
- After Phase 2, all user stories (Phase 3-7) can proceed in parallel

---

## Parallel Example: Foundational Phase

```text
# Launch all formatters in parallel (different files, no dependencies):
Task: T008 "Base formatter protocol in infrahub_sdk/ctl/formatters/base.py"
Task: T009 "Rich table formatter in infrahub_sdk/ctl/formatters/table.py"
Task: T010 "JSON formatter in infrahub_sdk/ctl/formatters/json.py"
Task: T011 "CSV formatter in infrahub_sdk/ctl/formatters/csv.py"
Task: T012 "YAML formatter in infrahub_sdk/ctl/formatters/yaml.py"

# Launch all formatter tests in parallel:
Task: T015 "Table formatter tests in tests/unit/ctl/formatters/test_table.py"
Task: T016 "JSON formatter tests in tests/unit/ctl/formatters/test_json.py"
Task: T017 "CSV formatter tests in tests/unit/ctl/formatters/test_csv.py"
Task: T018 "YAML formatter tests in tests/unit/ctl/formatters/test_yaml.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T018)
3. Complete Phase 3: User Story 1 - Query (T019-T023)
4. **STOP and VALIDATE**: `infrahub get <kind>` works with all output formats
5. Demo/review if ready

### Incremental Delivery

1. Setup + Foundational → CLI skeleton with formatters ready
2. Add US1 (Query) → MVP: read-only data access
3. Add US2 (Create) → Users can populate data
4. Add US3 (Update) → Full data management
5. Add US4 (Delete) → Complete CRUD lifecycle
6. Add US5 (Schema) → Self-service discovery
7. Polish → Production-ready

### Parallel Agent Strategy

With multiple agents:

1. Complete Setup + Foundational together
2. Once Foundational is done, dispatch in parallel:
   - Agent A: US1 (Query) + US5 (Schema) — both read-only
   - Agent B: US2 (Create) + US3 (Update) — both write operations
   - Agent C: US4 (Delete) — standalone
3. All stories integrate independently via enduser_commands.py

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Unit tests mock the SDK client; integration tests hit a real Infrahub instance
- Commit after each phase or logical task group
- Stop at any checkpoint to validate independently
