---

description: "Task list for INFP-532: field selection with `only` and known-state field access"
---

# Tasks: Field Selection with `only` and Known-State Field Access

**Input**: Design documents from `specs/infp-532-field-selection-only/` ([spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/public-api.md](contracts/public-api.md), [quickstart.md](quickstart.md), [critique](critiques/critique-20261002-1.md))

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required. Constitution V asks for tests in the same change, written before the implementation they cover, asserting concrete values, and run on **both** the async (`InfrahubClient`) and sync (`InfrahubClientSync`) paths. Use the existing `client_types = ["standard", "sync"]` / `@pytest.mark.parametrize("client_type", client_types)` pattern from `tests/unit/sdk/test_node.py`, the `clients` fixture from `tests/unit/sdk/conftest.py`, `httpx_mock` for HTTP, and `client.schema.set_cache(...)` for schemas.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: The user story the task belongs to (US1–US4)
- All paths are relative to the repository root

## Conventions for every task

- Follow `AGENTS.md` and `.agents/rules/code-comments.md`. Comment only non-obvious intent, never reference specs, tasks or tickets in code, and use `# type: ignore[<code>]` only with justification.
- Every new public parameter is appended **last** in its signature (research R13). Async and sync signatures must stay identical, because `tests/unit/sdk/test_client.py::test_validate_method_signature` checks this.
- Never edit `infrahub_sdk/protocols.py` or anything under `docs/docs/python-sdk/sdk_ref/` by hand.
- Before each commit: `uv run invoke format lint-code`. For markdown: `uv run invoke lint-docs`.

---

## Phase 1: Setup (Shared Test Scaffolding)

**Purpose**: Test modules and fixtures that the later phases fill in.

- [X] T001 [P] Create `tests/unit/sdk/test_node_field_access.py` with module docstring, `client_types = ["standard", "sync"]`, and helper fixtures. (1) A `location_payload` builder that returns a GraphQL edge for `location_schema` (from `tests/unit/sdk/conftest.py`) and takes a set of keys to omit, so tests can build nodes whose payload lacks `description`, `primary_tag` or `tags`. (2) A helper `make_node(client_type, clients, schema, data)` that returns `InfrahubNode` or `InfrahubNodeSync`.
- [X] T002 [P] Create `tests/unit/sdk/test_node_selection.py` with `client_types` and fixtures for a generic family: a `GenericSchemaAPI` `TestGenericDevice` (attributes `name`, `description`; cardinality-many relationship `tags` of kind `Generic` to `BuiltinTag`) with `used_by=["TestRouter", "TestSwitch"]`. `TestRouter` is a `NodeSchemaAPI` inheriting it and adding attribute `role`. `TestSwitch` inherits it and adds attribute `ports`. Add a fixture that loads these, plus `tag_schema` and `location_schema`, into `client.schema.set_cache(...)` for both clients (see `tests/unit/sdk/test_hierarchical_nodes.py:266` for the cache pattern).
- [X] T003 [P] Create `tests/unit/sdk/test_node_hydration.py` with `client_types` and fixtures: a `CoreStandardGroup`-like schema (`std_group_schema` from conftest) whose `members` relationship peers a generic `CoreNode`, and two concrete member kinds, one defining attribute `name` and one not. Register them with `client.schema.set_cache(...)`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error and warning types, the read-reporting module and the selection module. Every story depends on them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests (write first; they must fail before T007–T009)

- [X] T004 [P] Write `tests/unit/sdk/test_field_access.py`, covering:
  - (a) `build_unloaded_message(kind, field, selection)` returns exactly the three message forms in `contracts/public-api.md` § Message format: SDK selection, `Selection` with `peer_floor=True`, and `None` (origin unknown).
  - (b) `report_unloaded_read(...)` with strict off emits `FieldNotLoadedWarning` whose text is the message plus the 1.x suffix, and whose `filename` is this test file. That second point proves the stack level skips `infrahub_sdk` frames.
  - (c) With strict on, or with `strict=True` passed for the node, it raises `FieldNotLoadedError` with `.kind`, `.field`, `.selection` set and the message without the suffix.
  - (d) Inside `internal_field_access()` it neither warns nor raises, including from an `async def` decorated with the decorator.
  - (e) Two reports from the same call site with different node ids produce one warning under the default filter: run them in a `warnings.catch_warnings()` block with `simplefilter("default")` and assert `len(record) == 1`.
- [X] T005 [P] Write `tests/unit/sdk/test_selection.py`, covering:
  - `check_selection_conflict` raises `SelectionConflictError` (with `.parameters`) for `only` with `include=[]`, `include=[...]`, `exclude=[]` and `exclude=[...]`, and passes for `only` alone and for `include` with `exclude`.
  - `validate_only` accepts attribute, relationship, hierarchical (when `supports_hierarchy`) and floor names. It raises `SelectionFieldNotFoundError` naming the field for unknown names. For a generic, it accepts implementing-kind-only names when `fragment=True` and, when `fragment=False`, raises with `.implementing_kinds` set and a message mentioning `fragment=True`.
  - `Selection.describe()` returns `only=['name']`, `exclude=['description']`, `include=['tags'], exclude=['description']`, `default selection`, and the peer form `peer of InfraDevice.site, fetched with only=['site']`. `Selection.for_peer(...)` copies `strict`.
  - The decision helpers (`is_attribute_selected`, `is_relationship_selected`, `should_expand_peer`, `is_hierarchical_selected`) implement the rules in `research.md` R9, including today's rules when `only is None`.
- [X] T006 [P] Write tests in `tests/unit/sdk/test_exceptions.py` (create if absent) asserting that `FieldNotLoadedError`, `SelectionFieldNotFoundError` and `SelectionConflictError` are direct subclasses of `Error` (`__bases__ == (Error,)`) and are not subclasses of `AttributeError`, `UninitializedError` or `ValueError`. Also assert that `FieldNotLoadedWarning` subclasses `FutureWarning`.

### Implementation

- [X] T007 Add `FieldNotLoadedError(Error)` (attributes `kind`, `field`, `selection: str | None`), `SelectionFieldNotFoundError(Error)` (attributes `kind`, `field`, `implementing_kinds: list[str]`), `SelectionConflictError(Error)` (attribute `parameters: list[str]`) and `FieldNotLoadedWarning(FutureWarning)` to `infrahub_sdk/exceptions.py`, following the `__init__`-sets-`self.message` pattern of the existing classes.
- [X] T008 Create `infrahub_sdk/node/selection.py`. Per `data-model.md` § Selection and `research.md` R7–R9, it contains:
  - `IDENTITY_FLOOR_NAMES = frozenset({"id", "hfid", "display_label"})` and `HIERARCHICAL_FIELD_NAMES = ("parent", "children", "ancestors", "descendants")`.
  - A frozen dataclass `Selection` with fields `only`, `include`, `exclude` (tuples or `None`), `strict: bool`, `peer_of: str | None = None` and `peer_floor: bool = False`. It provides `Selection.from_args(include, exclude, only)` (strict iff `only is not None`), `Selection.for_peer(parent, parent_kind, rel_name, peer_floor)` and `describe()`.
  - `check_selection_conflict(include, exclude, only)`.
  - `validate_only(only, schema, implementing_schemas, fragment, kind)`.
  - Pure decision helpers: `is_attribute_selected(name, include, exclude, only)`, `is_relationship_selected(rel_schema, include, exclude, only)`, `should_expand_peer(rel_name, include, only, prefetch_relationships)` and `is_hierarchical_selected(name, include, exclude, only, prefetch_relationships)`.
  - It must not import `node.py` (no circular imports).
- [X] T009 Create `infrahub_sdk/node/field_access.py`, containing:
  - `_STRICT_FIELD_ACCESS: bool = False` (the single switch).
  - `_INTERNAL_ACCESS: ContextVar[bool]` with `internal_field_access()` (context manager) and `with_internal_field_access` (decorator that works on sync functions and coroutine functions, using `inspect.iscoroutinefunction`).
  - `build_unloaded_message(kind, field, selection)`.
  - `report_unloaded_read(kind, field, selection, strict)`, which returns silently when internal access is active, raises `FieldNotLoadedError` when `_STRICT_FIELD_ACCESS or strict`, and otherwise calls `warnings.warn(message + " This will raise FieldNotLoadedError in infrahub-sdk 2.0.", FieldNotLoadedWarning, stacklevel=_external_stacklevel())`.
  - `_external_stacklevel()`, which walks `sys._getframe()` until the first frame whose filename is not under the `infrahub_sdk` package directory.

  Make T004 and T005 pass.
- [X] T010 Add `"error::infrahub_sdk.exceptions.FieldNotLoadedWarning"` to `[tool.pytest.ini_options].filterwarnings` in `pyproject.toml`. Run `uv run pytest tests/unit -q -p no:randomly` to confirm the suite still passes, since nothing emits the warning yet. Note that tests asserting the warning must use `pytest.warns(FieldNotLoadedWarning)`, which overrides the filter locally.

**Checkpoint**: Foundation ready. T004–T006 pass, and the full unit suite is green.

---

## Phase 3: User Story 1 — Unknown fields announce themselves (Priority: P1) 🎯 MVP

**Goal**: Every attribute and relationship has a known state (`is_loaded`). Reading an unknown field emits `FieldNotLoadedWarning` and returns today's value. The SDK's own reads stay silent.

**Independent Test**: `uv run pytest tests/unit/sdk/test_node_field_access.py tests/unit/ctl/formatters tests/unit/sdk/test_transfer_importer.py -q`, with every case parametrised over both clients, plus the full unit suite green under the warnings-as-errors filter.

### Tests for User Story 1 (write first; they must fail before T016)

- [X] T011 [P] [US1] In `tests/unit/sdk/test_node_field_access.py`, write the access matrix for `Attribute.value` and `Attribute.is_loaded` on both clients. Cover every row of the FR-018 table in `data-model.md`:
  - Key present with a value: no warning, `is_loaded` `True`.
  - Key present with `{"value": None}`: no warning.
  - Key absent on a node with `id`: `pytest.warns(FieldNotLoadedWarning, match=...)` with the exact message for origin unknown, value `None`, `is_loaded` `False`.
  - Key absent on a node without `id`: no warning, `None`, `is_loaded` `True`.
  - Assigning to an absent attribute: then readable without warning.
  - A new node saved through a mocked `…Create` mutation (`httpx_mock` returning `{"ok": true, "object": {"id": "abc"}}`): a never-set attribute then warns and a set one does not.

  Also assert that `node.<attr>.is_loaded` itself never warns.
- [X] T012 [P] [US1] In `tests/unit/sdk/test_node_field_access.py`, write the same matrix for cardinality-one relationships (`location_schema.primary_tag`), covering `id`, `hfid`, `hfid_str`, `display_label`, `typename`, `kind`, `initialized`, `peer`, `get()` and `is_loaded`. Assert that `initialized` keeps today's value (`False` for a present relationship with `{"node": null}`) with no warning when present. Assert that assigning `node.primary_tag = "<id>"` makes it known. Cover a hierarchical `parent` using the `hierarchical_schema` fixture from `tests/unit/sdk/test_hierarchical_nodes.py` (copy it or import it).
- [X] T013 [P] [US1] In `tests/unit/sdk/test_node_field_access.py`, write the matrix for cardinality-many relationships (`location_schema.tags`), covering `peers`, `peer_ids`, `peer_hfids`, `peer_hfids_str`, `is_from_profile`, `[0]`, iteration and `is_loaded`:
  - Unknown on a fetched node: warns and returns `[]`.
  - New node: `[]` with no warning.
  - Present with `{"edges": []}`: no warning.
  - After `fetch()` (mocked): known.
  - `initialized` never warns and keeps its meaning.
  - `add()` on an unknown manager still raises `UninitializedError`.
  - Setting `manager.peers = [...]` and `manager.peers.append(...)` still work.
- [X] T014 [P] [US1] In `tests/unit/sdk/test_node_field_access.py`, write the internal-read regression tests on both clients:
  - (a) A node built from a payload missing `description` and `tags`, stored with `client.store.set(node=node)`: no warning (the filter makes any warning fail the test).
  - (b) Using the `schema_with_hfid` fixture, a node whose HFID traverses a relationship and is built with that relationship absent: `node.hfid` is `None` with no warning. The node is retrievable with `client.store.get(key=node.id)` and not by HFID.
  - (c) Modify one attribute and `save()` through a mocked `…Update` mutation. Capture the request with `httpx_mock.get_requests()` and assert that the mutation input contains only `id` and the modified attribute.
  - (d) `save(allow_upsert=True)` on a new node: no warning.
  - (e) `node.get_path_value("primary_tag__name__value")` on an unknown relationship: `None`, silently.
- [X] T015 [P] [US1] Add tests to `tests/unit/ctl/formatters/test_table.py`, `test_json.py`, `test_yaml.py` and `test_csv.py`: a node built with `description` and `tags` absent renders without those fields (or with them blank, per the formatter's existing convention for missing values) and raises no warning. Also create `tests/unit/sdk/test_transfer_importer.py`: `LineDelimitedJSONImporter.remove_and_store_optional_relationships()` on nodes built from default-selection payloads (cardinality-many keys absent) skips those relationships and raises no warning.

### Implementation for User Story 1

- [X] T016 [US1] In `infrahub_sdk/node/attribute.py`:
  - Add `_present: bool = True`, `_owner: InfrahubNodeBase | None = None` (behind `TYPE_CHECKING`), and `_bind(owner, present)`.
  - Add the `is_loaded` property (`self._present or self._owner is None or not self._owner.id`).
  - Make the `value` getter call `self._owner._report_unloaded_read(self.name)` when not loaded, then return `self._value`. Make the setter also set `_present = True`.
  - Switch internal methods (`_initialize_graphql_payload`, `is_from_pool_attribute`, `is_unresolved_pool_attribute`, `_generate_mutation_query`) to read `self._value` instead of `self.value`.
- [X] T017 [P] [US1] In `infrahub_sdk/node/related_node.py`:
  - On `RelatedNodeBase`, add `_present`, `_owner`, `_bind(owner, present)` and `is_loaded`, with the same rule as T016.
  - Add a private `_check_loaded()` that calls `self._owner._report_unloaded_read(self.name)` when not loaded, and call it at the top of the detected accessors (`id`, `hfid`, `hfid_str`, `display_label`, `typename`, `kind`, `initialized`) and of `RelatedNode.get()` / `RelatedNodeSync.get()`.
  - Inside `get()`, `hfid_str`, `initialized` and `_generate_input_data`, read the private fields (`_peer`, `_id`, `_hfid`, `_typename`) so one read produces one report.
- [X] T018 [P] [US1] In `infrahub_sdk/node/relationship.py`:
  - Replace the `self.peers` instance attribute with `self._peers` and a `peers` property plus setter on `RelationshipManagerBase`.
  - Add `is_loaded` on `RelationshipManager` and `RelationshipManagerSync` (`self.initialized or not self.node.id`) and a `_check_loaded()` reporting through `self.node._report_unloaded_read(self.name)`.
  - Call it in the `peers` getter, `peer_ids`, `peer_hfids`, `peer_hfids_str`, `is_from_profile` and `__getitem__`.
  - Switch `add`, `extend`, `remove`, `_generate_input_data` and `fetch` to `self._peers`.
- [X] T019 [US1] In `infrahub_sdk/node/node.py` (`InfrahubNodeBase`):
  - Add `self._selection: Selection | None = None` in `__init__` before `_init_attributes`.
  - Add `_report_unloaded_read(self, field: str) -> None`, which calls `field_access.report_unloaded_read(self._schema.kind, field, self._selection, strict=bool(self._selection and self._selection.strict))`.
  - In `_init_attributes`, call `attr._bind(self, present=isinstance(data, dict) and attr_schema.name in data)`.
  - Decorate `_generate_input_data`, `_strip_unmodified`, `_generate_mutation_query`, `_validate_upsert`, `get_path_value` and `get_human_friendly_id` with `with_internal_field_access`.
- [X] T020 [US1] In `infrahub_sdk/node/node.py` (`InfrahubNode` and `InfrahubNodeSync`):
  - In `_init_relationships`, bind every cardinality-one `RelatedNode` and hierarchical `parent` with `present = isinstance(data, dict) and rel_schema.name in data`.
  - In `__setattr__`, bind the newly built `RelatedNode` with `present=True`.
  - Decorate `_process_mutation_result` (async and sync) with `with_internal_field_access`.

  Make T011–T014 pass on both clients.
- [X] T021 [P] [US1] In `infrahub_sdk/ctl/formatters/base.py` (`_extract_relationship_value`, `extract_node_data`, the detail builder) and `infrahub_sdk/ctl/formatters/yaml.py`: skip any attribute or relationship whose `is_loaded` is `False` before reading its value. Make the T015 formatter tests pass.
- [X] T022 [P] [US1] In `infrahub_sdk/ctl/object/update.py`, run `_relationship_changed` and `_apply_relationship` under `internal_field_access()` from `infrahub_sdk.node.field_access`, so that comparing and rewriting an unfetched relationship emits nothing.
- [X] T023 [P] [US1] In `infrahub_sdk/transfer/importer/json.py` (`remove_and_store_optional_relationships`), skip relationships whose `is_loaded` is `False` before reading `peer_ids` or `id`. Make the T015 importer test pass.
- [X] T024 [US1] Run `uv run pytest tests/unit -q`. For every existing test that now fails with `FieldNotLoadedWarning`, either widen the fixture payload so the field is present, or wrap the read in `pytest.warns(FieldNotLoadedWarning)` when the test is about that read. Don't change any assertion on a fetched value. List the files touched in the commit message.

**Checkpoint**: User Story 1 is complete and shippable on its own as the 1.x deprecation step.

---

## Phase 4: User Story 2 — Exclusive selection with `only` (Priority: P2)

**Goal**: `get`, `all` and `filters` accept `only`, producing exactly the named fields plus the floor. Conflicts and unknown names are rejected before the data query. Nodes from `only` raise on unknown reads in 1.x. First-party narrowing call sites use `only`.

**Independent Test**: `uv run pytest tests/unit/sdk/test_node_selection.py tests/unit/sdk/test_group_context.py tests/unit/ctl/test_generator.py -q`, both clients.

### Tests for User Story 2 (write first; they must fail before T030)

- [X] T025 [P] [US2] In `tests/unit/sdk/test_node_selection.py`, write query-shape tests on both clients, using `generate_query_data(...)` and asserting the full expected dict:
  - `only=["name"]` on `tag_schema`: the envelope is exactly `id`, `display_label`, `__typename`, plus `name`.
  - `only=[]`: the floor only.
  - `only=["name", "hfid"]`: also `hfid`.
  - `only=["id", "display_label"]`: same as `only=[]`.
  - `only=["primary_tag"]` and `only=["tags"]` on `location_schema`: the peer floor `id`, `hfid`, `display_label`, `__typename` with no peer attributes.
  - Attribute-kind cardinality-many relationship not named: absent.
  - `only` with `prefetch_relationships=True`: named relationships carry the peer's default set, and unnamed ones stay absent.
  - Hierarchical fields (`hierarchical_schema`): absent unless named; named → floor; named plus prefetch → expanded.
  - Generic `TestGenericDevice` with `fragment=True` and `only=["name", "role"]`: the generic part has `name`, the `...on TestRouter` fragment has `role`, and `...on TestSwitch` is empty or absent.
- [X] T026 [P] [US2] In `tests/unit/sdk/test_node_selection.py`, write regression tests asserting that default queries are unchanged (SC-004). For `location_schema` and `tag_schema` with no selection arguments, with `include=["tags"]`, with `exclude=["description"]` and with both, the generated dict equals a literal expected dict that includes the envelope `hfid`. Also write the SC-008 test: generate `only=["name"]` for `tag_schema`, add two attributes and a relationship to a copy of the schema, regenerate, and assert equality.
- [X] T027 [P] [US2] In `tests/unit/sdk/test_node_selection.py`, write rejection tests on both clients using `client.filters`, `client.all` and `client.get`:
  - `only` with `include` or `exclude` (including empty lists) raises `SelectionConflictError`.
  - An unknown name raises `SelectionFieldNotFoundError` naming it.
  - A generic name only on an implementing kind with `fragment=False` raises with `implementing_kinds == ["TestRouter"]`.

  In every case, assert that `httpx_mock.get_requests()` contains no request to `/graphql`.
- [X] T028 [P] [US2] In `tests/unit/sdk/test_node_selection.py`, write behaviour tests on both clients, with mocked GraphQL responses:
  - Nodes from `filters(only=["name"])` raise `FieldNotLoadedError` (not a warning) when reading `description.value` and `tags.peers`. The error has `.selection == "only=['name']"`.
  - With `only=["primary_tag"]` and no prefetch, the peer is not in `client.store`, and `node.primary_tag.peer` raises `NodeNotFoundError` whose message contains `fetch()` and `prefetch_relationships`.
  - With `only=["primary_tag"], prefetch_relationships=True`, the peer node is stored. Reading one of its cardinality-many relationships raises `FieldNotLoadedError` whose selection label starts with `peer of BuiltinLocation.primary_tag`.
- [X] T029 [P] [US2] Write first-party call-site tests:
  - `tests/unit/sdk/test_group_context.py`: `get_group()` (async and sync) sends a query whose `members` carries only the peer floor and no member attributes. Check the request body with `httpx_mock.get_requests()`.
  - `tests/unit/ctl/test_generator.py`: the group lookup query uses `only=["members"]`, so the members edge has the floor only.
  - `tests/unit/sdk/test_client.py`: `get_list_repositories` requests only `name`, `location`, `commit`, `ref` and `internal_status` (plus the floor) with fragments.

### Implementation for User Story 2

- [X] T030 [US2] In `infrahub_sdk/node/node.py`, `InfrahubNodeBase.generate_query_data_init`: append `only: list[str] | None = None`, call `check_selection_conflict(include, exclude, only)`, and build `edges.node` as `{"id", "display_label", "__typename"}` plus `"hfid"` when `only is None or "hfid" in only`. Update the docstring.
- [X] T031 [US2] In `infrahub_sdk/node/node.py`, `InfrahubNode.generate_query_data_node` and `_process_hierarchical_fields`: append `only`, and replace the inline selection conditions with the `selection.py` helpers. Under `only`, a named relationship gets `peer_data = {}` (the floor) unless `prefetch_relationships`, in which case the peer's default `generate_query_data_node(property=..., include_metadata=...)` is used. Hierarchical fields follow `is_hierarchical_selected`. Keep today's behaviour exactly when `only is None`.
- [X] T032 [US2] In `infrahub_sdk/node/node.py`, `InfrahubNode.generate_query_data`: append `only` and pass it to `generate_query_data_init` and `generate_query_data_node`. For generics with `fragment=True` under `only`, the generic part receives the names defined on the generic. Each child receives `child_only = [n for n in only if n not in generic field names and n is defined on the child]`, called with `inherited=True`, and the fragment is omitted when empty (research R9). Leave the `exclude_child` path untouched when `only is None`.
- [X] T033 [US2] Mirror T031 and T032 in `InfrahubNodeSync.generate_query_data_node`, `_process_hierarchical_fields` and `generate_query_data` in `infrahub_sdk/node/node.py`, using the same helpers.
- [X] T034 [US2] In `infrahub_sdk/client.py` (`InfrahubClient`), make these changes to `get`, `all` and `filters`, including every `@overload`:
  - Append `only: list[str] | None = None` as the last explicit parameter (before `**kwargs`), and forward it from `get` and `all` to `filters`.
  - In `filters`, call `check_selection_conflict` before `self.schema.get`. After resolving the schema, validate `only` with `validate_only`, fetching implementing-kind schemas through `self.schema.get(kind=k, branch=branch)` for each `schema.used_by` when the schema is a generic.
  - Build `selection = Selection.from_args(include, exclude, only)` and pass it, with `only`, into `generate_query_data` and `_process_nodes_and_relationships`.
  - In `_process_nodes_and_relationships`, set `node._selection = selection` immediately after `from_graphql`, before `_process_relationships`.
  - Process relationships when `prefetch_relationships`, or when `only is None and include and any(...)`.
  - Document `only` in all three docstrings next to `include` and `exclude`.
- [X] T035 [US2] Mirror T034 in `InfrahubClientSync.get`, `all`, `filters` and `_process_nodes_and_relationships` in `infrahub_sdk/client.py`. Run `uv run pytest tests/unit/sdk/test_client.py -q -k "signature or method_count"`.
- [X] T036 [US2] In `infrahub_sdk/node/node.py`, `InfrahubNode._process_relationships` and `InfrahubNodeSync._process_relationships`: after each `from_graphql` for a peer, set `related_node._selection = Selection.for_peer(self._selection, self._schema.kind, rel_name, peer_floor=False)` when `self._selection` is set.
- [X] T037 [P] [US2] In `infrahub_sdk/node/related_node.py`, `RelatedNode.get` and `RelatedNodeSync.get`: when the store lookup raises `NodeNotFoundError` and `self._peer` is `None`, re-raise `NodeNotFoundError` with the same `identifier`, `branch_name` and `node_type`, and with a message that names the relationship and says to call `fetch()` on it or query with `prefetch_relationships=True`. Use `raise ... from exc`.
- [X] T038 [US2] Migrate the first-party call sites to `only` (FR-032):
  - `infrahub_sdk/query_groups.py`: `get_group` (async and sync) uses `only=["members"]`.
  - `infrahub_sdk/ctl/generator.py:70` and `infrahub_sdk/ctl/check.py:159` use `only=["members"]`.
  - `infrahub_sdk/client.py`: `get_list_repositories` (async and sync) uses `only=["name", "location", "commit", "ref", "internal_status"]` with the existing `fragment=True`.

  Make T025–T029 pass on both clients.

**Checkpoint**: User Stories 1 and 2 both work on their own.

---

## Phase 5: User Story 3 — Controlled peer hydration (Priority: P3)

**Goal**: `RelatedNode.fetch` and `RelationshipManager.fetch` accept `only` and `exclude`. Names are validated once against the declared peer kind and sent per concrete kind.

**Independent Test**: `uv run pytest tests/unit/sdk/test_node_hydration.py -q`, both clients.

### Tests for User Story 3 (write first; they must fail before T040)

- [X] T039 [P] [US3] In `tests/unit/sdk/test_node_hydration.py`, write tests on both clients:
  - (a) `RelatedNode.fetch(only=["name"])` sends one query for the peer's concrete typename selecting `name` plus the floor. The peer then raises `FieldNotLoadedError` on another attribute.
  - (b) `RelationshipManager.fetch(only=["name"])` on members of two kinds, one lacking `name`, sends one `filters` query per kind. The kind lacking `name` selects the floor only.
  - (c) An unknown name raises `SelectionFieldNotFoundError` with no GraphQL request sent.
  - (d) `fetch(only=[...], exclude=[...])` raises `SelectionConflictError`.
  - (e) An uninitialized manager's re-query uses `only=["members"]`. Inspect the first request body.
  - (f) `fetch()` with no arguments behaves as today: default selection, members stored.

### Implementation for User Story 3

- [X] T040 [US3] In `infrahub_sdk/node/relationship.py`, give `RelationshipManager.fetch` and `RelationshipManagerSync.fetch` the signature `fetch(self, only: list[str] | None = None, exclude: list[str] | None = None) -> None`. Then:
  - Call `check_selection_conflict(None, exclude, only)`.
  - When `only is not None`, resolve the declared peer schema (`self.client.schema.get(kind=self.schema.peer, branch=self.branch)`) and its implementing schemas, then call `validate_only(..., fragment=True)` once.
  - Replace the uninitialized re-query with `only=[self.schema.name]`.
  - Per concrete kind, resolve its schema and pass `only=[n for n in only if n is a field of that kind]` (or `exclude=exclude`) to the batched `client.filters`.
  - Update the docstrings.
- [X] T041 [US3] In `infrahub_sdk/node/related_node.py`, give `RelatedNode.fetch` and `RelatedNodeSync.fetch` the signature `fetch(self, timeout=None, priority=None, only: list[str] | None = None, exclude: list[str] | None = None)`. Apply the same conflict check, validation against `self.schema.peer` and filtering to `self.typename`'s fields, then pass `only` or `exclude` to `client.get`. Update the docstrings. Make T039 pass.

**Checkpoint**: User Stories 1–3 all work on their own.

---

## Phase 6: User Story 4 — Strict access switch for 2.0 (Priority: P4)

**Goal**: Flipping `_STRICT_FIELD_ACCESS` turns every 1.x warning into `FieldNotLoadedError` with the same message, and leaves silent cases silent.

**Independent Test**: `uv run pytest tests/unit/sdk/test_node_field_access.py -q -k strict`, both clients.

- [ ] T042 [US4] In `tests/unit/sdk/test_node_field_access.py`, add a `strict_access` fixture (`monkeypatch.setattr("infrahub_sdk.node.field_access._STRICT_FIELD_ACCESS", True)`) and a strict-mode variant of the T011–T014 matrices. Every row that warned now raises `FieldNotLoadedError`, with `str(err)` equal to the warning text minus the 1.x suffix. Every silent row stays silent: new-node reads, present fields, `is_loaded`, `RelationshipManager.initialized`, save, store and HFID. If any row fails, fix `infrahub_sdk/node/field_access.py` or the reporting call site, not the test.

**Checkpoint**: The 2.0 change is a one-line edit.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T043 [P] In `docs/docs/python-sdk/guides/query_data.mdx`:
  - Add a section "Selecting exactly the fields you need with `only`" (the identity floor, `hfid` when named, references versus `prefetch_relationships`, conflicts, hydration with `fetch(only=...)`).
  - Add a section "Fields that were not fetched" (`is_loaded`, the warning and its 2.0 plan, the fix path, early opt-in with `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning`, and `getattr`/`hasattr` defaults no longer masking reads in strict mode).
  - Correct line 197 and line 364 (`include` expands peers in full), the `exclude` example at lines 401-412 (`device.site` is a reference whose value is unknown, not `None`), and the cardinality-many example at lines 336-359 (reading `peers` warns).

  Every example uses async/sync `Tabs` per `docs/AGENTS.md`.
- [ ] T044 [P] Add changelog fragments:
  - `changelog/+infp-532-only.added.md` (`only` on `get`/`all`/`filters`, `fetch(only=..., exclude=...)`, `is_loaded`)
  - `changelog/+infp-532-field-access.deprecated.md` (reading a field that wasn't fetched now emits `FieldNotLoadedWarning` and will raise `FieldNotLoadedError` in 2.0; how to fix; how to opt in early)
  - `changelog/+infp-532-call-sites.changed.md` (group lookups and repository listing use `only`; group lookups no longer push members into the store; CLI output skips fields that weren't fetched)

  Follow the style of `changelog/+ipaddress-attribute-kind.added.md`.
- [ ] T045 [P] Add integration tests to `tests/integration/test_node.py`, for both clients. Against a live server: `only=["name"]` returns nodes exposing `name` and the floor, reading `description.value` raises `FieldNotLoadedError`, and `fetch(only=["name"])` on a relationship makes exactly that peer field readable. They need Docker (testcontainers). If Docker is unavailable, record "not run" in the implementation report.
- [ ] T046 Run `uv run invoke docs-generate`, then `uv run invoke docs-validate`, and commit the regenerated `docs/docs/python-sdk/sdk_ref/**` and `docs/docs/infrahubctl/**` files.
- [ ] T047 Run `uv run invoke format lint-code` (ruff, ty, mypy) and `uv run invoke lint-docs`, and fix every finding without new suppressions, or with a justified `# type: ignore[<code>]` where unavoidable.
- [ ] T048 Run `uv run pytest tests/unit -q` and walk through `quickstart.md` scenarios 1–5 and 7. Confirm SC-001, SC-004, SC-005, SC-006, SC-007 and SC-008 against their tests, and note each in the implementation report.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. T001–T003 run in parallel.
- **Foundational (Phase 2)**: depends on Setup. T004–T006 run in parallel. T007 → T008 → T009 (T009 imports T007's types). T010 needs T007.
- **US1 (Phase 3)**: depends on Foundational. Tests T011–T015 run in parallel. Then T016, T017 and T018 run in parallel (different files). T019 and T020 depend on T016–T018 (same file, so run them in order). T021, T022 and T023 run in parallel after T019 and T020. T024 comes last.
- **US2 (Phase 4)**: depends on US1, because strict raising and `Selection` binding rely on the known-state reporting. Tests T025–T029 run in parallel. Then T030 → T031 → T032 → T033 (same file, in order). T034 → T035 (same file). T036 needs T034. T037 can run in parallel with T030–T036. T038 comes last.
- **US3 (Phase 5)**: depends on US2 (`filters(only=...)`). T039, then T040 and T041 in parallel (different files).
- **US4 (Phase 6)**: depends on US1 only. It can run in parallel with US2 and US3.
- **Polish (Phase 7)**: depends on all stories. T043, T044 and T045 run in parallel, then T046 → T047 → T048.

### User story dependencies

```text
Setup → Foundational → US1 ──┬──▶ US2 ──▶ US3 ──┐
                             └──▶ US4 ──────────┴──▶ Polish
```

## Parallel Examples

```text
# Phase 2 tests together
T004 tests/unit/sdk/test_field_access.py
T005 tests/unit/sdk/test_selection.py
T006 tests/unit/sdk/test_exceptions.py

# User Story 1: field classes together, after its tests
T016 infrahub_sdk/node/attribute.py
T017 infrahub_sdk/node/related_node.py
T018 infrahub_sdk/node/relationship.py

# User Story 1: first-party readers together, after T019–T020
T021 infrahub_sdk/ctl/formatters/{base,yaml}.py
T022 infrahub_sdk/ctl/object/update.py
T023 infrahub_sdk/transfer/importer/json.py

# User Story 2 tests together
T025–T028 tests/unit/sdk/test_node_selection.py (sections)
T029 tests/unit/sdk/test_group_context.py, tests/unit/ctl/test_generator.py, tests/unit/sdk/test_client.py
```

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 → Phase 2 → Phase 3.
2. **Stop and validate**: the access matrix passes on both clients, and the full unit suite is green under the warnings-as-errors filter.
3. This is shippable as the 1.x deprecation step: warnings with no new API beyond `is_loaded`.

### Incremental delivery

1. US1 is the deprecation signal, plus `is_loaded`.
2. US2 adds `only`: the feature developers asked for, strict from day one, and first-party call sites migrated.
3. US3 adds precise hydration.
4. US4 makes the 2.0 switch mechanical.
5. Polish covers docs, changelog, integration tests and generated reference docs.

## Notes

- `[P]` tasks touch different files and have no dependency on an incomplete task.
- Every behavioural test runs on both clients.
- Commit after each task or logical group, with `uv run invoke format lint-code` first.
- Keep default (no `only`) queries identical to today's. T026 guards this.
