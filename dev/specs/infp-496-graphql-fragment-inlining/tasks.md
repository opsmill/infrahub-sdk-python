# Tasks: GraphQL Fragment Inlining — SDK Scope

**Input**: `python_sdk/dev/specs/infp-496-graphql-fragment-inlining/spec.md`
**Parent tasks**: `specs/infp-496-graphql-fragment-inlining/tasks.md` (full feature view including backend)
**Scope**: All work inside `python_sdk/` only (FR-015: all fragment logic lives in the SDK)

**Path note**: All file paths below are relative to the **infrahub repo root** (e.g.,
`python_sdk/infrahub_sdk/...`). The `python_sdk/` directory is a git submodule — changes inside
it must be committed separately from the main infrahub repo.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Setup (Fixture Repository)

**Purpose**: Create the fixture repository used by SDK unit tests and backend component tests.
All fixture files live inside the `python_sdk` submodule.

- [*] T001 Create fixture repo directory structure at `python_sdk/tests/fixtures/repos/fragment_inlining/` (subdirectories: `fragments/`, `queries/`)
- [*] T002 [P] Create `python_sdk/tests/fixtures/repos/fragment_inlining/fragments/interfaces.gql` (defines `interfaceFragment`, `portFragment`) and `python_sdk/tests/fixtures/repos/fragment_inlining/fragments/devices.gql` (defines `deviceFragment` that spreads `...interfaceFragment`, and `chassisFragment`)
- [*] T003 [P] Create `python_sdk/tests/fixtures/repos/fragment_inlining/queries/query_two_files.gql` (spreads `...interfaceFragment` and `...deviceFragment`), `query_no_fragments.gql` (no spreads), `query_transitive.gql` (spreads `...deviceFragment` only), `query_missing_fragment.gql` (spreads `...undeclaredFragment`)
- [*] T004 Create `python_sdk/tests/fixtures/repos/fragment_inlining/.infrahub.yml` declaring `graphql_fragments` (both fragment files under `fragments/`) and `graphql_queries` (all four query files under `queries/`)

---

## Phase 2: Foundational (SDK Core — Blocking Prerequisites)

**Purpose**: Exception types, config model, and renderer are needed by all user story phases.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Add `GraphQLQueryError` base class plus five typed exception classes (`QuerySyntaxError`, `FragmentNotFoundError`, `DuplicateFragmentError`, `CircularFragmentError`, `FragmentFileNotFoundError`) to `python_sdk/infrahub_sdk/exceptions.py` — all use `__init__`-based pattern, all extend `GraphQLQueryError`; update `handle_exception()` in `ctl/utils.py` to also catch `GraphQLQueryError`
- [x] T006 Add `InfrahubRepositoryFragmentConfig` class with `name: str`, `file_path: Path`, and `load_fragments(relative_path: str = ".") -> list[str]` method to `python_sdk/infrahub_sdk/schema/repository.py` — mirror the existing `InfrahubRepositoryGraphQLConfig` pattern
- [x] T007 Add `graphql_fragments: list[InfrahubRepositoryFragmentConfig] = Field(default_factory=list)` field to `InfrahubRepositoryConfig` in `python_sdk/infrahub_sdk/schema/repository.py`
- [x] T008 Add **public** functions `build_fragment_index(fragment_files: list[str]) -> dict[str, FragmentDefinitionNode]` and `collect_required_fragments(query_doc: DocumentNode, fragment_index: dict[str, FragmentDefinitionNode]) -> list[str]` to `python_sdk/infrahub_sdk/graphql/query_renderer.py`
- [x] T009 Add `render_query_with_fragments(query_str: str, fragment_files: list[str]) -> str` to `python_sdk/infrahub_sdk/graphql/query_renderer.py`; early-return when query has no fragment spreads (FR-011); also raises `QuerySyntaxError` for invalid syntax in query or fragment files
- [x] T009b Create `python_sdk/infrahub_sdk/graphql/query_renderer.py` with `render_query(name: str, config: InfrahubRepositoryConfig, relative_path: str = ".") -> str` — high-level entry point used by CLI: loads query + fragment files from the configuration, delegates to `render_query_with_fragments`

**Checkpoint**: SDK core complete — all test and CLI phases can now proceed

---

## Phase 3: User Story 1 — Basic Fragment Import (Priority: P1) 🎯 MVP

**Goal**: The renderer correctly inlines required fragments from multiple files and excludes
unreferenced ones. Repository configuration parses `graphql_fragments` YAML correctly.

**Independent Test**:

```bash
cd python_sdk && uv run pytest tests/unit/sdk/graphql/test_fragment_renderer.py -v
cd python_sdk && uv run pytest tests/unit/sdk/test_repository.py -v -k fragment
```

- [ ] T010 [P] [US1] Write unit tests covering: single direct spread from one file → renders correctly; spreads across two files → both rendered; no spreads → query returned unchanged; same spread used twice → definition appears once; surplus definitions excluded — in `python_sdk/tests/unit/sdk/graphql/test_fragment_renderer.py`
- [ ] T011 [P] [US1] Write unit tests covering: `InfrahubRepositoryConfig` parses `graphql_fragments` YAML section; `load_fragments()` with a file path returns single-element list with file content; `load_fragments()` with a directory path returns one entry per `.gql` file (sorted alphabetically); `load_fragments()` raises `FragmentFileNotFoundError` for a path that does not exist — in `python_sdk/tests/unit/sdk/test_repository.py`

**Checkpoint**: US1 SDK work fully tested and independently verifiable

---

## Phase 4: User Story 2 — Transitive Fragment Dependencies (Priority: P2)

**Goal**: `collect_required_fragments` resolves transitive spreads so both A and its dependency B
are included even when the query only references A directly.

**Independent Test**:

```bash
cd python_sdk && uv run pytest tests/unit/sdk/graphql/test_fragment_renderer.py -v -k transitive
```

- [ ] T013 [P] [US2] Write unit tests covering: transitive dependency across two files (query spreads `...deviceFragment`; `deviceFragment` spreads `...interfaceFragment` in a different file → both definitions in output); only directly/transitively required fragments included, not all from the files — in `python_sdk/tests/unit/sdk/graphql/test_fragment_renderer.py`

**Checkpoint**: US1 + US2 SDK logic fully tested

---

## Phase 5: User Story 4 — Graceful Failure for Unresolved Fragments (Priority: P2)

**Goal**: All four error types are raised correctly under their documented conditions.

**Independent Test**:

```bash
cd python_sdk && uv run pytest tests/unit/sdk/graphql/test_fragment_renderer.py -v -k error
```

- [ ] T014 [P] [US4] Write unit tests covering: `FragmentNotFoundError` raised when spread references name absent from all fragment files; `DuplicateFragmentError` raised when same name appears in two separate content strings; `DuplicateFragmentError` raised when same name appears twice within one content string; `CircularFragmentError` raised for A→B→A cycle — in `python_sdk/tests/unit/sdk/graphql/test_fragment_renderer.py`

**Checkpoint**: All renderer error paths tested

---

## Phase 6: infrahubctl CLI Integration (enables US1 + US4 for local workflows)

**Goal**: `infrahubctl` local execution paths apply fragment rendering automatically when
`graphql_fragments` is declared in `.infrahub.yml` (FR-016).

**Independent Test**: Run `infrahubctl run` pointing at the fixture repository; the query executes
without unresolved-spread errors.

- [x] T019 [P] [US1] Update `execute_graphql_query()` in `python_sdk/infrahub_sdk/ctl/utils.py`: replace `query_object.load_query()` with `render_query(name=query, config=repository_config)` from `query_renderer.py`
- [x] T020 [P] [US1] Update `transform()` in `python_sdk/infrahub_sdk/ctl/cli_commands.py`: replace `repository_config.get_query(name=...).load_query()` with `render_query(name=transform.query, config=repository_config)` from `query_renderer.py`

**Checkpoint**: Both server sync and infrahubctl CLI paths apply fragment rendering

---

## Phase 7: Polish & SDK-Specific Concerns

- [ ] T021 [P] Run `cd python_sdk && uv run invoke format lint-code` to verify no ruff/mypy violations in modified files (`exceptions.py`, `schema/repository.py`, `graphql/query_renderer.py`, `ctl/utils.py`, `ctl/cli_commands.py`)
- [ ] T022 Run `cd python_sdk && uv run invoke docs-generate` to regenerate SDK CLI + configuration docs after docstring additions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user story phases
- **US1 (Phase 3)**: Depends on Phase 2; T010 and T011 are independent [P]
- **US2 (Phase 4)**: Depends on Phase 2 (renderer transitive logic already in T008)
- **US4 (Phase 5)**: Depends on Phase 2 (error types in T005, error logic in T008)
- **CLI Integration (Phase 6)**: Depends on Phase 2; T019 and T020 are independent [P]
- **Polish (Phase 7)**: After all phases complete

### Parallel Opportunities

```bash
# Phase 1 — after T001 completes:
T002  python_sdk/tests/fixtures/repos/fragment_inlining/fragments/*.gql
T003  python_sdk/tests/fixtures/repos/fragment_inlining/queries/*.gql

# Phase 3 — after Phase 2 completes:
T010  python_sdk/tests/unit/sdk/graphql/test_fragment_renderer.py
T011  python_sdk/tests/unit/sdk/test_repository.py

# Phase 6 — after Phase 2 completes (independent of Phase 3):
T019  python_sdk/infrahub_sdk/ctl/utils.py
T020  python_sdk/infrahub_sdk/ctl/cli_commands.py
```

---

## Notes

- `python_sdk/` is a git submodule — commit changes there separately from the main Infrahub repository
- Run `cd python_sdk && uv run invoke format lint-code` before committing any Python changes
- Run `cd python_sdk && uv run invoke docs-generate` after any docstring or CLI command changes
- Backend integration tasks (updating `backend/infrahub/git/integrator.py` and writing component tests) are in `specs/infp-496-graphql-fragment-inlining/tasks.md`
