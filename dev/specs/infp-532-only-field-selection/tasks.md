---
description: "Task list for fetching only the named fields with only (INFP-532)"
---

# Tasks: Fetch Only the Named Fields with `only`

**Input**: Design documents from `specs/infp-532-only-field-selection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/public-api.md, quickstart.md

**Tests**: included. Constitution V requires tests in the same change, written before the code they cover, on both clients. SC-001 to SC-005 are checked by tests.

**Organization**: grouped by user story. User Story 1 (P1) is the first increment that can ship on its own. User Story 2 (P2) depends on it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 or US2; setup, foundational and polish tasks have no story label

## Path Conventions

Single Python library. Production code is under `infrahub_sdk/`, tests under `tests/`. Paths are relative to the repository root (`specs/` is a link to `dev/specs/`).

## Rules for every task

- Every behaviour is tested on the async and the sync client (`@pytest.mark.parametrize("client_type", client_types)` as in `tests/unit/sdk/test_node.py`, or the `BothClients` fixture from `tests/unit/sdk/conftest.py`).
- Test cases are dataclasses with `name` first, passed with `pytest.param(case, id=case.name)`. Every `pytest.raises` has `match=`. Assertions compare concrete values. No `unittest.mock`; use `httpx_mock` and `monkeypatch` only (`.agents/rules/python-testing.md`).
- No reference to the ticket, the spec, FR or SC numbers, or user stories in code, comments, docstrings or test names (`.agents/rules/code-comments.md`).
- Do not edit any existing query-generation test (SC-003). Do not change `infrahub_sdk/ctl/`, `infrahub_sdk/transfer/`, `infrahub_sdk/query_groups.py`, `infrahub_sdk/protocols.py` or `infrahub_sdk/exceptions/catalogue.py` (plan, "Not changed").
- Run `uv run invoke format lint-code` before each commit.

---

## Phase 1: Setup

**Purpose**: confirm a clean starting point.

- [X] T001 Install dependencies with `uv sync --all-groups --all-extras` and run `uv run pytest tests/unit/sdk/ -q` on the unchanged tree. Record the pass count in the commit message of the first code commit, as the baseline for SC-003.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the error types, the shared helpers, and the "the response contained this field" record with `is_loaded`. Both user stories need them.

**⚠️ No user story work starts until this phase is complete.**

### Tests first

- [X] T002 [P] Add tests for the three new errors in `tests/unit/sdk/test_exceptions.py`: `FieldNotLoadedError(kind, field, only, peer_of=None)` names the kind, the field and the `only` list, and the relationship when `peer_of` is set; `FieldNotFoundError(kind, field)` names the field and the kind; `FieldSelectionConflictError()` names `only`, `include` and `exclude`. Each keeps its arguments as attributes (contract §5).
- [X] T003 [P] Add tests for the private helpers in `tests/unit/sdk/test_node_only_helpers.py`, with schemas built in the test or taken from `tests/unit/sdk/conftest.py`:
  - **conflict check**: raises when `only` is set and `include` or `exclude` is not `None`, including empty lists; passes when either side is `None` (research R2).
  - **name check**: accepts attributes, relationships, `id`, `display_label` and `hfid`. It accepts `parent`, `children`, `ancestors` and `descendants` only for a hierarchical kind. For a generic kind, it accepts names of the generic or of any implementing kind. Any other name raises `FieldNotFoundError` naming the field and the kind (research R3).
  - **strict peer check**: a name missing on one of several peer kinds raises (research R10).
  - **HFID expansion**: `name__value` gives the attribute `name`. `location__name__value` gives the relationship `location` with the peer attribute `name`. A kind with no HFID gives nothing. For a generic kind, each implementing kind uses its own HFID: `Cat` from `infrahub_sdk/testing/schemas/animal.py` (research R5).
- [ ] T004 [P] Add `is_loaded` tests on nodes not from `only` in `tests/unit/sdk/test_node_only_access.py` (contract §3, data-model "record"), on both clients:
  - attribute, cardinality-one relationship, cardinality-many relationship, `parent`, `children`, `ancestors` and `descendants`, present and absent in the data;
  - `{"node": null}` counts as present;
  - assignment of an attribute value, of a relationship and of `peers` makes the field loaded;
  - `fetch()` on a manager makes it loaded;
  - a new node (no `id`) has every field loaded; after a mocked save gives it an `id`, the fields it never set are not loaded;
  - `RelatedNode` objects inside a manager are always loaded;
  - `is_loaded` never raises;
  - reading any field on these nodes returns what it returns today (no `FieldNotLoadedError`).

### Implementation

- [X] T005 Add `FieldNotLoadedError`, `FieldNotFoundError` and `FieldSelectionConflictError` to `infrahub_sdk/exceptions/base.py` (each with `Error` as its only base, messages per contract §5, arguments kept as attributes, following `FragmentNotFoundError`). Add them to `base.__all__`, to the import block and `__all__` in `infrahub_sdk/exceptions/__init__.py`, and to `tests/fixtures/error_catalogue/public_names.json`. Make T002 pass and keep `tests/unit/sdk/test_exceptions_public_names.py`, `tests/unit/sdk/test_exceptions_layering.py` and `tests/unit/sdk/test_exceptions.py` green.
- [X] T006 Create the private module `infrahub_sdk/node/_only.py` with the conflict check, the name check (kind schema plus implementing kinds' schemas passed in), the strict peer check, the HFID expansion and the frozen marker dataclass (`only` tuple, `peer_of`). It takes schemas already looked up and does no I/O (plan, Design Notes). Make T003 pass.
- [ ] T007 Add the record and `is_loaded` to `Attribute` in `infrahub_sdk/node/attribute.py`. Add a private `_bind(node, present)`. The `value` setter marks the attribute as loaded. `is_loaded` follows data-model "`is_loaded`". Switch `_initialize_graphql_payload`, `is_from_pool_attribute` and `is_unresolved_pool_attribute` to read `_value` (research R8).
- [ ] T008 Add the record, `_bind` and `is_loaded` to `RelatedNode` and `RelatedNodeSync` (shared base) in `infrahub_sdk/node/related_node.py`. Make `initialized` read the cached peer, `_id` and `_hfid` directly (research R8, condition list).
- [ ] T009 In `infrahub_sdk/node/relationship.py`:
  - make `peers` a property backed by `_peers`, with a setter that marks the manager as loaded and a getter that returns the stored list itself;
  - switch every internal read and write (`__init__`, `add`, `extend`, `remove`, `fetch`, `_generate_input_data`, `is_from_profile`, `__getitem__`) to `_peers`;
  - add `_bind` and `is_loaded` (based on `initialized` and the setter flag), on both manager classes.

  Do not add `__len__` or `__bool__` (research R8).
- [ ] T010 In `infrahub_sdk/node/node.py`, for `InfrahubNode` and `InfrahubNodeSync`, bind every field object with `present = name in data`:
  - in `_init_attributes`;
  - in `_init_relationships`, for both copies of `parent` and `children` and for `_hierarchical_data`;
  - for the `RelatedNode` built by `__setattr__` when a relationship is assigned, which is marked as assigned.

  Add the private marker attribute (default `None`) and the private HFID-peer slot (default empty). Make T004 pass.
- [ ] T011 [P] Add `is_loaded` to the `Attribute` and `RelatedNodeBase` protocols in `infrahub_sdk/protocols_base.py` (research R12).

**Checkpoint**: `uv run pytest tests/unit/sdk/ -q` passes with the baseline count plus the new tests. No existing test was edited.

---

## Phase 3: User Story 1 - Fetch only the named fields (Priority: P1) 🎯 first increment

**Goal**: `get()`, `all()` and `filters()` accept `only`. The query contains only the named fields plus `id`, `display_label` and `__typename`. Nodes from `only` raise `FieldNotLoadedError` on reads of fields they do not carry. Saving, upserting, the HFID and the store keep working.

**Independent test**: with `httpx_mock`, call `all(kind=..., only=[...])` on both clients against the test schemas. Check the request body, the nodes returned, which reads raise, and that `is_loaded` is `False` exactly for those reads.

### Tests for User Story 1 (write first, confirm they fail)

- [ ] T012 [P] [US1] Query-generation tests in `tests/unit/sdk/test_node_only_query.py` that call the new private query methods on both node classes and compare the whole generated query (research R4, R5; contract §1). Cases:
  - `only=["name"]`;
  - `only=[]`;
  - `id` and `display_label`;
  - a cardinality-one and a cardinality-many relationship as references;
  - `prefetch_relationships=True` expanding only named relationships;
  - `parent`, `children`, `ancestors`, `descendants` as references when named; with `prefetch_relationships`, with the hierarchy generic's default fields, and no unnamed hierarchy field added;
  - `hfid` through an attribute and through a relationship (`schema_with_hfid`), merged with a named relationship and with `prefetch_relationships`;
  - a kind with no HFID;
  - a generic kind: a name on the generic, a name only on some implementing kinds under `__alias__Kind__name`, and per-kind HFID;
  - `fragment=True` adding nothing;
  - `property=True` and `include_metadata=True` on named fields;
  - filters, `order`, `partial_match`, `offset`, `limit` and `count` unchanged.

  The node never requests `hfid`.
- [ ] T013 [P] [US1] Schema-growth test in `tests/unit/sdk/test_node_only_query.py`: the same `only` call gives the same query after an attribute and a relationship are added to the kind and to another implementing kind, when they are not named in `only` (SC-002).
- [ ] T014 [P] [US1] Client tests in `tests/unit/sdk/test_client_only.py`, on both clients, with `httpx_mock`:
  - **errors before any request**: `get`, `all` and `filters` raise `FieldSelectionConflictError`, and no request is recorded (including the schema request in `get`). A misspelt name raises `FieldNotFoundError` and no GraphQL query is recorded.
  - **names on generic and hierarchical kinds**: a name only on an implementing kind is accepted. `ancestors` is accepted on a hierarchical kind and rejected on a kind without a hierarchy.
  - **requests**: the body of the GraphQL request equals the expected query.
  - **nodes and peers**: nodes carry the marker. Under `prefetch_relationships`, peer nodes are built and stored only for named relationships (for hierarchy fields: `parent` and `children`, as today's prefetch does). A relationship that only an implementing kind has gets its peer built and stored (research R9, critique E1).
  - **edge case**: `device.site.peer` raises `NodeNotFoundError` when the site is not in the store.
  - **HFID**:
    - `node.hfid` is calculated with `populate_store=True` and with `populate_store=False`;
    - `client.store.get(key=node.hfid, kind=...)` returns the node from `only`;
    - `node.hfid` does not change after a later query stores a narrower copy of the peer;
    - `node.hfid` is `None` when its HFID fields were not fetched and `hfid` was not named.
  - **store**: a node from `only` replaces a fuller copy in the store, and reading its unfetched fields from the store raises.
- [ ] T015 [P] [US1] Read tests in `tests/unit/sdk/test_node_only_access.py`, on both clients, for nodes from `only` and peers returned with them. Every row of the contract §4 table:
  - raises `FieldNotLoadedError` when the field is not loaded, with a message naming the kind, the field and the `only` list (and the relationship for a peer);
  - does not raise when the field is loaded.

  The "never raises" reads do not raise. `get_path_value`, `get_flat_value`, `matches_local_checksum`, `download_file(skip_if_unchanged=True)` and `upload_if_changed` raise when the field they read was not fetched (research R13). `is_loaded` is `False` in exactly the raising cases (SC-005).
- [ ] T016 [P] [US1] Tests for operations that must not raise, in `tests/unit/sdk/test_node_only_access.py`, on both clients, on a node from `only` with every other field unfetched (research R8, contract §4):
  - `save()` for create and update;
  - `create(allow_upsert=True)`;
  - `update()`;
  - `hfid`, `hfid_str`, `get_human_friendly_id()`, `get_human_friendly_id_as_string()`;
  - `client.store.set(node)`;
  - processing a mutation result;
  - `repr()`.

  Check the update mutation body: it holds `id` and the changed fields only, so unfetched fields are neither sent nor cleared.

### Implementation for User Story 1

- [ ] T017 [US1] In `infrahub_sdk/node/node.py`, add the private query methods for `only` to `InfrahubNode`, using the `_only.py` helpers and the existing peer-query helpers (`RelatedNode._generate_query_data`, `RelationshipManager._generate_query_data`, `generate_query_data_node` for prefetched peers) (research R4, R5, R14):
  - **queried node**: `id`, `display_label`, `__typename`, no `hfid`;
  - **named fields**: named attributes; named relationships as references;
  - **prefetch**: default fields for named peers when `prefetch_relationships` is set;
  - **hierarchy fields**: when named, references, or with `prefetch_relationships` the peer fields `_process_hierarchical_fields` requests today;
  - **generic kinds**: `...on Kind` blocks with the existing alias form, using implementing kinds' schemas from the query's branch;
  - **HFID**: expanded paths;
  - **`property` and `include_metadata`**: applied to the named fields;
  - **query arguments**: filters, `order`, `partial_match`, `offset` and `limit` as `generate_query_data_init` does.

  The public `generate_query_data*` methods stay unchanged. Make the async rows of T012 and T013 pass.
- [ ] T018 [US1] Mirror T017 in `InfrahubNodeSync` in `infrahub_sdk/node/node.py`. Make the sync rows of T012 and T013 pass.
- [ ] T019 [US1] Raising accessors in `infrahub_sdk/node/attribute.py`, `infrahub_sdk/node/related_node.py` and `infrahub_sdk/node/relationship.py`: each "raises on" read in contract §4 checks `is_loaded` and the node's marker, and raises `FieldNotLoadedError` built from the marker, the node's kind and the field name. Reads on nodes without the marker are unchanged.
- [ ] T020 [US1] In `infrahub_sdk/node/node.py`, for both node classes:
  - add a private, non-raising version of `get_path_value`, which treats a field that is not loaded as missing and looks for a peer in the HFID-peer slot first, then through the cached peer and the store; make `get_human_friendly_id` use it;
  - leave the public `get_path_value` reading through the public accessors;
  - give `_process_relationships` a private argument with the relationship names to process, which reads from the node's data with aliases removed. Without the argument, its behaviour is unchanged (research R5, R8, R9).
- [ ] T021 [US1] In `infrahub_sdk/client.py`, `InfrahubClient`:
  - add `only: list[str] | None = None` as the last named parameter of `get` (6 overloads and the implementation), `all` (2 and the implementation) and `filters` (2 and the implementation), before `**kwargs`. Pass it from `get` and `all` to `filters`.
  - put the conflict check first in all three methods.
  - in `filters`, after the schema lookup: look up the implementing kinds' schemas with `branch`, run the name check, and call the private query method when `only` is not `None`.
  - in `_process_nodes_and_relationships`, under `only`: set the marker on each node; build peer nodes only for named relationships with `prefetch_relationships` (for hierarchy fields, `parent` and `children` as today) and for HFID paths; set the peer marker with `peer_of`; fill the HFID-peer slot. Add the peers to the related nodes that go to the store.

  Document `only` in the docstrings of `all` and `filters` next to `include` and `exclude`, and add a docstring to `get` that documents it.
- [ ] T022 [US1] Mirror T021 in `InfrahubClientSync` in `infrahub_sdk/client.py`. Run `tests/unit/sdk/test_client.py::test_validate_method_signature` and `test_method_sanity`.
- [ ] T023 [US1] Update the `Raises:` sections of `get_path_value`, `get_flat_value`, `matches_local_checksum`, `download_file` and `upload_if_changed` on both node classes in `infrahub_sdk/node/node.py` (research R16).

**Checkpoint**: T012 to T016 pass on both clients, and `uv run pytest tests/unit/sdk/ -q` passes without any existing test edited. User Story 1 can ship on its own here.

---

## Phase 4: User Story 2 - Fetch chosen fields of a peer (Priority: P2)

**Goal**: `fetch(only=[...])` on both relationship classes returns peers with only the named fields, checks the names before any peer query, and works on relationships that a node from `only` did not load.

**Independent test**: on a device from `only=["site"]`, `device.site.fetch(only=["name"])` sends one query with the expected fields, `device.site.peer.name.value` returns the name, and reading `device.site.peer.description.value` raises. Cardinality-many cases are covered as well.

### Tests for User Story 2 (write first, confirm they fail)

- [ ] T024 [P] [US2] Tests in `tests/unit/sdk/test_relationship_only.py`, on both clients, with `httpx_mock` (research R10, contract §2):
  - **`RelatedNode.fetch(only=["name"])`**:
    - sends one query with `id`, `display_label`, `__typename` and `name`;
    - the peer is readable and raises on `description`;
    - `device.site.hfid` keeps the server value after `fetch(only=["description"])`.
  - **`RelatedNode.fetch()` on a relationship that is not loaded**: raises `FieldNotLoadedError` on a node from `only`, and `Error` on a default node.
  - **`RelationshipManager.fetch(only=[...])`, mixed peer kinds**: a name missing on one kind raises `FieldNotFoundError` and no peer query is sent.
  - **misspelt name on a manager that is not loaded**: raises, and no request is sent.
  - **reload on a node from `only`**: uses `get(..., only=[name], populate_store=False)`. The request body is checked, and the store still holds the developer's node.
  - **`ancestors` and `descendants`**: `ancestors.fetch(only=[...])` and `descendants.fetch(only=[...])` on a node from `only` load the peers.
  - **peers from `fetch(only=...)`**: they carry the marker and raise on unfetched fields.
  - **without `only`**: `fetch()` on both classes behaves as today.

### Implementation for User Story 2

- [ ] T025 [US2] In `infrahub_sdk/node/related_node.py`:
  - add `only: list[str] | None = None` as the last parameter of `RelatedNode.fetch` and `RelatedNodeSync.fetch`, and pass it to `client.get`;
  - when the cached peer is a node from `only` and its HFID cannot be calculated, make `hfid` and `hfid_str` return the HFID the reference carried;
  - update the `Raises:` sections.
- [ ] T026 [US2] In `infrahub_sdk/node/relationship.py`, add `only: list[str] | None = None` to `RelationshipManager.fetch` and `RelationshipManagerSync.fetch`. Steps, in order:
  1. Check the names against `self.schema.peer`, before any request.
  2. If the manager is not loaded, reload it. On a node from `only`, use `client.get(kind=..., id=..., only=[self.schema.name], populate_store=False)`. On any other node, keep the existing reload.
  3. Run the strict check against every actual peer kind.
  4. Add one `filters(..., only=only)` per peer kind to the batch.

  Update the `Raises:` sections.

**Checkpoint**: T024 passes on both clients, and the full unit suite passes.

---

## Phase 5: Polish and cross-cutting concerns

- [ ] T027 [P] Integration tests in `tests/integration/test_node_only.py`, following `tests/integration/test_infrahub_client.py` and `tests/integration/test_infrahub_client_sync.py` (one test class per client). Use `SchemaAnimal` from `infrahub_sdk/testing/schemas/animal.py`.
  - `all(kind="TestingDog", only=["name", "owner"])` returns dogs with `name`, and `breed` raises.
  - `all(kind="TestingAnimal", only=["name", "breed"])` returns `breed` for dogs and cats.
  - `only=["hfid"]` on `TestingCat` gives `node.hfid` with the cat's own three HFID parts.
  - `dog.owner.fetch(only=["name"])` makes the owner's name readable.
  - Saving a node from `only` after changing one attribute leaves its other fields unchanged on the server.
- [ ] T028 [P] Add the section on `only` to `docs/docs/python-sdk/guides/query_data.mdx` after "Excluding attribute and relationships". It covers:
  - `only`, `only=[]`, `id` and `display_label`;
  - `hfid` in `only`;
  - relationships as references, and `prefetch_relationships` with `only`;
  - hierarchy fields;
  - generic kinds;
  - `is_loaded` and `FieldNotLoadedError`;
  - the errors raised before a request.

  Add `fetch(only=...)` under "Fetching relationships manually". Make no claim about what `include` returns for peers. Add one sentence to `docs/docs/python-sdk/guides/store.mdx`: a node from `only` replaces a fuller copy of the same node, and `is_loaded` tells which fields it carries (research R16).
- [ ] T029 [P] Add `changelog/+only-field-selection.added.md`. It describes `only` on `get`, `all`, `filters` and `fetch`, `is_loaded`, and the three new errors, in the style of the existing fragments in `changelog/`.
- [ ] T030 Run `uv run invoke docs-generate` and commit the regenerated pages under `docs/docs/python-sdk/sdk_ref/`. Then run `uv run invoke docs-validate`. Check that `infrahub_sdk/node/_only.py` gets no reference page; if it does, exclude it in `tasks.py` the way other private modules are.
- [ ] T031 Run `uv run invoke format lint-code` and `uv run invoke lint-docs`. Fix every new finding without silencing a rule, unless an inline reason is given (constitution IV, VI).
- [ ] T032 Run `uv run pytest tests/unit/ -q` and `uv run pytest tests/integration/test_node_only.py -q`. Confirm that `git diff origin/infrahub-develop -- tests/unit/sdk/test_node.py tests/unit/sdk/test_hierarchical_nodes.py` shows no changed lines (SC-003).
- [ ] T033 Check the scope with `git diff --stat origin/infrahub-develop`. Only the files listed in plan.md "Source Code" and the regenerated docs may change. Run `grep -rn "INFP-532\|FR-0\|SC-0\|User Story" infrahub_sdk tests` and confirm it returns nothing.
- [ ] T034 Run the checks in [quickstart.md](./quickstart.md) sections 1, 2 and 4.

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. Blocks both user stories.
- **User Story 1 (Phase 3)**: after Foundational.
- **User Story 2 (Phase 4)**: after User Story 1. `fetch(only=...)` uses the `only` path of `get` and `filters` (T021, T022) and the raising accessors (T019).
- **Polish (Phase 5)**: after the stories it documents or tests. T027 and T028 need both stories.

### Task dependencies inside phases

- T005 needs T002. T006 needs T003 and T005. T007 to T010 need T004, and T010 needs T007 to T009.
- T017 needs T006 and T012. T018 needs T017.
- T019 needs T007 to T010 and T015.
- T020 needs T017 and T018.
- T021 needs T017, T019, T020 and T014. T022 needs T021.
- T016 passes once T019 and T020 are done.
- T025 and T026 need T024 and T022.
- T030 needs T023, T025 and T026 (docstrings).

### Parallel opportunities

- Phase 2 tests: T002, T003 and T004 (different files).
- T011 runs alongside T007 to T010.
- Phase 3 tests: T012 to T016 can be written together (T015 and T016 share a file; write them in sequence if one person does both).
- Phase 5: T027, T028 and T029.

## Parallel example: User Story 1

```text
Task: "Query-generation tests in tests/unit/sdk/test_node_only_query.py"   (T012, T013)
Task: "Client tests in tests/unit/sdk/test_client_only.py"                  (T014)
Task: "Read and must-not-raise tests in tests/unit/sdk/test_node_only_access.py" (T015, T016)
```

## Implementation strategy

1. **First increment**: Phases 1 to 3. `only` on the query methods, with errors, `is_loaded` and the HFID. Ship once the checkpoint passes; User Story 2 adds to it without changing it.
2. **Second increment**: Phase 4, `fetch(only=...)`.
3. **Finish**: Phase 5, integration tests, docs, changelog and checks. Docs and changelog ship in the same pull request as the code (constitution VII).

Commit after each task or logical group, with `uv run invoke format lint-code` run first.
