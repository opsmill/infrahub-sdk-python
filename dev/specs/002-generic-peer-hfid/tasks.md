# Tasks: Reference generic peers by HFID in object files

**Input**: Design documents from `specs/002-generic-peer-hfid/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/object-file-reference.md, quickstart.md

**Tests**: Required. The constitution (Principle V) requires tests in the same change, and a test that reproduces the reported failure.

**Organization**: Tasks are grouped by user story. Every code change is in `infrahub_sdk/spec/object.py`, so implementation tasks in that file run one after another. Tasks in test files can run in parallel with each other.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (a different file, and no dependency on an incomplete task)
- **[Story]**: the user story the task belongs to (US1, US2, US3)

---

## Phase 1: Setup (shared test fixtures)

**Purpose**: give the unit tests and integration tests a schema in which a relationship points to a generic without an HFID.

- [X] T001 [P] Add a pytest fixture `schema_generic_peer_data` to `tests/unit/sdk/spec/test_object.py`. It returns a schema dict in the same `{"main": ..., "nodes": [...], "generics": [...]}` shape as `tests/fixtures/schema_01.json`, with these parts:
  - Generic `TestingSupportsSubintf`: no `human_friendly_id`, `used_by: ["TestingPhysicalInterface", "TestingPortChannelInterface"]`, and relationship `sub_interfaces` with identifier `supports_subintf__subinterface`.
  - Nodes `TestingPhysicalInterface` and `TestingPortChannelInterface`: both `inherit_from: ["TestingSupportsSubintf"]`, both with attribute `name` and a cardinality-one relationship `device` to `TestingDevice`, and both with `human_friendly_id: ["device__name__value", "name__value"]`.
  - Node `TestingDevice`: attribute `name` and `human_friendly_id: ["name__value"]`.
  - Node `TestingSubInterface`: attributes `name` and `vlan_id`, and relationship `parent_interface` (cardinality one, optional, peer `TestingSupportsSubintf`, identifier `supports_subintf__subinterface`).
  - Node `TestingTunnel`: relationship `source_interfaces` (cardinality many, peer `TestingSupportsSubintf`).
  - Node `TestingOther`, which does not inherit from the generic and has an HFID, for the "wrong kind" tests.
  - Node `TestingNoHfid`, which inherits from the generic and has no HFID.

  Add `client_with_generic_peer_schema`, which calls `client.schema.set_cache(schema=..., branch="main")` as `client_with_schema_01` does in `tests/unit/sdk/conftest.py:1739`.
- [X] T002 [P] Add the same schema as an `infrahub_sdk.schema.SchemaRoot` (namespace `Testing`) in a new class-scoped fixture `schema_generic_peer` inside a new test class `TestSpecObjectGenericPeer(TestInfrahubDockerClient)` in `tests/integration/test_spec_object.py`. Load it with `client.schema.load(..., wait_until_converged=True)` in an `initial_schema` fixture, following `TestSpecObject.initial_schema`. Leave out `TestingOther` and `TestingNoHfid`; those are for unit tests only.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: classify `{kind, hfid}` mappings as references and record whether the declared peer is a generic without an HFID. All stories depend on this phase.

- [X] T003 Add a test to `tests/unit/sdk/spec/test_object.py` that reproduces the failure. Load `TestingSubInterface` data with `parent_interface: [router1, Gi0/0/3]` using `client_with_generic_peer_schema`. Assert that `get_relationship_info` returns `format == RelationshipDataFormat.ONE_REF` and `peer_has_hfid is False`. Also assert the new field `peer_is_generic_without_hfid is True`, which fails before T005.
- [X] T004 In `infrahub_sdk/spec/object.py`, add the helper `is_hfid_reference_dict(value: Any) -> bool`. It returns true when `value` is a dict that contains `hfid` and does not contain `data`. Extend `validate_list_of_hfids` (line 26) so that items for which `is_hfid_reference_dict` is true are accepted.
- [X] T005 In `infrahub_sdk/spec/object.py`, add two fields to `RelationshipInfo` (line 80):
  - `peer_is_generic_without_hfid: bool = False`
  - `peer_used_by: list[str] = Field(default_factory=list)`

  In `get_relationship_info` (line 144), make these changes:
  - Fetch the declared peer schema (`rel_schema.peer`) and set both fields when it is a `GenericSchemaAPI` with no `human_friendly_id`.
  - Change the check at line 152 so that a dict for which `is_hfid_reference_dict` is true is not rejected.
  - Add a branch that sets `ONE_REF` for a cardinality-one dict for which `is_hfid_reference_dict` is true.
  - Keep the existing `"kind" in value` handling at line 156, so that `peer_human_friendly_id` comes from the named kind.

**Checkpoint**: T003 passes, and every existing test in `tests/unit/sdk/spec/test_object.py` still passes.

---

## Phase 3: User Story 1 - Reference a generic peer by naming its kind and HFID (Priority: P1) (MVP)

**Goal**: `parent_interface: {kind: TestingPhysicalInterface, hfid: [router1, Gi0/0/3]}` loads, and the mutation data contains `{"hfid": [...], "kind": "TestingPhysicalInterface"}`.

**Independent test**: the unit tests T006 and T007 pass, and the integration test T011 links one sub-interface to a physical interface and another to a port-channel.

### Tests for User Story 1

- [X] T006 [P] [US1] In `tests/unit/sdk/spec/test_object.py`, add a parametrized test modelled on `test_hfid_normalization_in_object_loading` (line 344). It captures the `create` data from `obj.process()` for these cases:
  - Cardinality one with `{kind: TestingPhysicalInterface, hfid: [router1, Gi0/0/3]}`. Expected: `{"hfid": ["router1", "Gi0/0/3"], "kind": "TestingPhysicalInterface"}`.
  - Cardinality one with `{kind: TestingPortChannelInterface, hfid: [router1, Po1]}`.
  - Cardinality many (`TestingTunnel.source_interfaces`) with a list of two mappings.
  - A mapping whose `hfid` is a string, for a kind with a one-part HFID. Use `TestingDevice` through a relationship whose peer is `TestingDevice`. Expected: the string becomes a one-item list.
- [X] T007 [P] [US1] In `tests/unit/sdk/spec/test_object.py`, add a test that `RelatedNode` built from `{"hfid": [...], "kind": "TestingPhysicalInterface"}` produces `_generate_input_data() == {"hfid": [...], "kind": "TestingPhysicalInterface"}`. Use the existing `RELATED_NODE_PAYLOAD_TEST_CASES` pattern (line 400).

### Implementation for User Story 1

- [X] T008 [US1] In `infrahub_sdk/spec/object.py`, add the helper `normalize_kind_hfid_reference(value: dict) -> dict`. It returns `{"hfid": normalize_hfid_reference(value["hfid"]), "kind": value["kind"]}`, and the result is always a list. In `create_node`, apply it in the `ONE_REF` branch (line 491) when the value is such a dict. In the `MANY_REF` branch (line 488), apply it per item: dict items use the new helper, and other items keep today's `normalize_hfid_reference` logic.
- [X] T009 [US1] Confirm that `validate_related_nodes` (line 338-342) returns no format error for a cardinality-one dict reference and for a `MANY_REF` list with dicts. Extend the `isinstance` checks to accept `dict` for `ONE_REF`.
- [X] T010 [P] [US1] Add `tests/fixtures/spec_objects/generic_peer_subinterfaces01.yml`. It creates:
  - Devices `router1` and `router2`.
  - `TestingPhysicalInterface` `router1/Gi0/0/3` and `router2/Gi0/0/3`.
  - `TestingPortChannelInterface` `router1/Po1`.

  Then add `tests/fixtures/spec_objects/generic_peer_subinterfaces02.yml` with two `TestingSubInterface` items: one referencing `{kind: TestingPhysicalInterface, hfid: [router1, Gi0/0/3]}` and one referencing `{kind: TestingPortChannelInterface, hfid: [router1, Po1]}`.
- [X] T011 [US1] In `TestSpecObjectGenericPeer` in `tests/integration/test_spec_object.py`, add `test_load_with_kind`. It loads both files from T010 with `validate_format` and then `process`. It then queries each sub-interface with `prefetch_relationships=True` and asserts that `parent_interface.peer.get_kind()` and the `hfid` match the expected kind and `[router1, Gi0/0/3]` / `[router1, Po1]`.

**Checkpoint**: User Story 1 works on its own. A file that names kinds loads without schema changes.

---

## Phase 4: User Story 2 - Reference a generic peer by HFID alone (Priority: P2)

**Goal**: `parent_interface: [router2, Gi0/0/3]` resolves to the single matching inheriting node. When zero or more than one node matches, the load stops with `ObjectValidationError`.

**Independent test**: the unit tests T012–T014 pass with a mocked `client.get`, and the integration test T017 links to the physical interface and then fails after a port-channel with the same HFID is added.

### Tests for User Story 2

- [ ] T012 [P] [US2] In `tests/unit/sdk/spec/test_object.py`, patch `client.get` with an `AsyncMock`. Make it return a node for `TestingPhysicalInterface` and `None` for `TestingPortChannelInterface`. Load `parent_interface: [router2, Gi0/0/3]` and assert:
  - The `create` data is `{"hfid": ["router2", "Gi0/0/3"], "kind": "TestingPhysicalInterface"}`.
  - `client.get` was awaited with `hfid=["router2", "Gi0/0/3"]`, `raise_when_missing=False` and `branch` for each candidate kind.
- [ ] T013 [P] [US2] Same setup, with both kinds returning a node. Assert that `obj.process()` raises `ObjectValidationError`, and that `str(error)` contains `parent_interface`, `TestingPhysicalInterface`, `TestingPortChannelInterface` and `kind:`.
- [ ] T014 [P] [US2] Same setup, with both kinds returning `None`. Assert that `ObjectValidationError` is raised and that the message contains `TestingSupportsSubintf` and `router9`. Add one more case: when the reference has one part and no candidate kind has a one-part HFID, assert that `client.get` is never awaited and that the "no node matches" error is raised.

### Implementation for User Story 2

- [ ] T015 [US2] In `infrahub_sdk/spec/object.py`, add `InfrahubObjectFileData._resolve_generic_hfid(cls, client, rel_info, hfid, position, branch) -> dict` as a classmethod. It follows research R3:
  1. Normalize `hfid` to a list.
  2. For each kind in `rel_info.peer_used_by`, fetch the kind's schema and keep it if its `human_friendly_id` has the same length as the HFID.
  3. Call `await client.get(kind=k, hfid=hfid, branch=branch, raise_when_missing=False)` for each kept kind.
  4. Return `{"hfid": hfid, "kind": k}` for exactly one match. Otherwise raise `ObjectValidationError` with the messages in `contracts/object-file-reference.md`.

  Add the comment `# ponytail: one query per candidate kind, add a (kind, hfid) cache if large files become slow`.
- [ ] T016 [US2] In `create_node` (line 487-492), apply `_resolve_generic_hfid` when `rel_info.peer_is_generic_without_hfid` is true and the reference item is a string or list without a kind. Leave UUID strings unchanged (`is_valid_uuid`). For `MANY_REF`, resolve each such item.
- [ ] T017 [US2] In `TestSpecObjectGenericPeer` in `tests/integration/test_spec_object.py`, add `test_load_hfid_only`. It loads a fixture `tests/fixtures/spec_objects/generic_peer_subinterfaces03.yml` (`Gi0/0/3.20` on router2 with `parent_interface: [router2, Gi0/0/3]`) and asserts that the peer kind is `TestingPhysicalInterface`. Then add `test_load_hfid_only_ambiguous`:
  1. Create a `TestingPortChannelInterface` named `Gi0/0/3` on `router2` with `client.create(...).save()`.
  2. Load `generic_peer_subinterfaces04.yml`, which has the same kind of reference with a new sub-interface name.
  3. Assert that `ObjectValidationError` is raised.

**Checkpoint**: User Stories 1 and 2 both work. The original example file loads without changes.

---

## Phase 5: User Story 3 - Clear errors when a reference cannot be resolved (Priority: P3)

**Goal**: `validate_format` reports a wrong kind, a kind without an HFID, a wrong number of HFID parts and unknown keys, with the position in the file, and without querying nodes.

**Independent test**: the unit test T018 passes and asserts each message from `contracts/object-file-reference.md`.

### Tests for User Story 3

- [ ] T018 [P] [US3] In `tests/unit/sdk/spec/test_object.py`, add a parametrized test that calls `ObjectFile(...).validate_format(client=client_with_generic_peer_schema)` and asserts that `ValidationError` is raised and its message includes the expected text. The cases are:
  - `kind: TestingOther`. Expected text: "is not TestingSupportsSubintf and does not inherit from it".
  - `kind: TestingNoHfid`. Expected text: "has no human_friendly_id".
  - `hfid: [Gi0/0/3]` for `TestingPhysicalInterface`. Expected text: "expected 2 values".
  - Extra key `id`. Expected text: "only `kind` and `hfid` are allowed".

  Each message starts with the position (for example `1.parent_interface`). The test uses no `httpx_mock` node responses, which confirms that no node query is made.

### Implementation for User Story 3

- [ ] T019 [US3] In `infrahub_sdk/spec/object.py`, add `InfrahubObjectFileData._validate_kind_hfid_reference(cls, client, rel_info, value, position, branch) -> list[ObjectValidationError]` as a classmethod. It implements rules V1–V4 from `data-model.md` using `client.schema.get(kind=..., branch=...)` and `rel_info.peer_used_by`. If the declared peer is a node, V1 requires `kind == rel_schema.peer`. If it is a generic, V1 requires the kind to be in its `used_by`. Call it from `validate_related_nodes`:
  - In the `ONE_REF` branch, for a dict value.
  - In the `MANY_REF` branch, for each dict item, with position `[*position, idx + 1]`.

**Checkpoint**: all three stories work, and `infrahubctl object validate` reports schema errors without loading.

---

## Phase 6: Polish and cross-cutting concerns

- [ ] T020 [P] In `docs/docs/python-sdk/topics/object_file.mdx`, add a section "Reference a node through a generic relationship". It describes the `kind` plus `hfid` form, the HFID-alone lookup and its ambiguity error, using the sub-interface example from `contracts/object-file-reference.md`. It also states that validation does not check whether the peer exists.
- [ ] T021 [P] Add the towncrier fragment `changelog/+generic-peer-hfid.added.md`. It says that object files can reference peers of a generic relationship by kind plus HFID, or by HFID alone when exactly one inheriting node matches.
- [ ] T022 Run `uv run invoke format lint-code` and `uv run invoke lint-docs`, and fix every finding.
- [ ] T023 Run `uv run pytest tests/unit/sdk/spec/ tests/unit/ctl/object/` and confirm that every test passes, including the existing HFID normalization tests (FR-008).
- [ ] T024 Run the integration tests from `quickstart.md`: `uv run pytest tests/integration/test_spec_object.py -k GenericPeer -v`.
- [ ] T025 Check the minimum supported Infrahub server version in `docs/docs/python-sdk/reference/compatibility.mdx` against the release that added `RelatedNodeInput.kind` (server issue #4649). Record the result in the pull request description.

---

## Dependencies and execution order

- **Setup (T001, T002)**: no dependencies. T001 and T002 can run in parallel.
- **Foundational (T003–T005)**: depends on T001. Blocks all stories.
- **User Story 1 (T006–T011)**: depends on Phase 2.
- **User Story 2 (T012–T017)**: depends on Phase 2. It also edits the same `create_node` branches as T008, so do it after T008.
- **User Story 3 (T018–T019)**: depends on Phase 2 and can be done after US1 or in parallel with US2. T019 edits `validate_related_nodes`, which T009 also edits, so do it after T009.
- **Polish (T020–T025)**: after the stories it documents or verifies.

### Within each story

Write the tests first and confirm that they fail. Then implement in `infrahub_sdk/spec/object.py`. Then run the integration test.

## Parallel examples

```text
# Setup
T001 tests/unit/sdk/spec/test_object.py  ||  T002 tests/integration/test_spec_object.py

# User Story 1 tests and fixtures
T006, T007 (unit tests)  ||  T010 (YAML fixtures)

# User Story 2 tests
T012  ||  T013  ||  T014   (separate test functions; merge into the one file at the end)

# Polish
T020 docs  ||  T021 changelog
```

## Implementation strategy

1. **MVP**: Phases 1–3 (T001–T011). This unblocks the interfaces schema in the request: the engineer adds `kind:` to each reference and needs no schema change.
2. **Add User Story 2**: object files written as in the request (`[router1, Gi0/0/3]`) load without changes.
3. **Add User Story 3**: errors at validation time give clear messages.
4. **Polish**: docs, changelog, lint, compatibility check.
