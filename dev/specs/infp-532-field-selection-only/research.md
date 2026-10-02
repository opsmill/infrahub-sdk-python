# Research: Field Selection with `only` and Known-State Field Access

Phase 0 output for [plan.md](plan.md). Each entry records a decision, the reason for it, and the alternatives that were weighed. Code references are to the state of `infrahub-develop` at the time of planning.

## Current behaviour (baseline)

- Query generation lives in `InfrahubNode.generate_query_data_init` / `generate_query_data` / `generate_query_data_node` / `_process_hierarchical_fields`, duplicated almost line for line in `InfrahubNodeSync` (`infrahub_sdk/node/node.py`).
- The queried node's envelope is `{id, hfid, display_label, __typename}` (`generate_query_data_init`). Peer envelopes come from `RelatedNodeBase._generate_query_data` and `RelationshipManagerBase._generate_query_data`, both `{id, hfid, display_label, __typename}`.
- Naming a relationship in `include` triggers a full default-set expansion of the peer with no narrowing (`should_fetch_relationship = prefetch_relationships or (include is not None and rel_name in include)`, introduced by `17c1f6ae`, #513).
- `client.filters` builds the query, then `_process_nodes_and_relationships` turns each edge into a node via `from_graphql` and, when `prefetch_relationships` is set or any relationship is named in `include`, builds peer nodes with `_process_relationships` and stores them.
- `InfrahubNodeBase._init_attributes` passes `data.get(name)` to each `Attribute`, so "key absent" and "value null" look identical. `RelationshipManager.initialized` is `data is not None`. `RelatedNode.initialized` is `bool(id) or bool(hfid)`.
- Unfetched fields read as `None` (`Attribute.value`, `RelatedNode.id` and friends) or `[]` (`RelationshipManager.peers`, `peer_ids`, `peer_hfids`, indexing).
- The pytest configuration does not turn warnings into errors.

## R1. Where the known-state lives

**Decision**: Each field object records whether its value was *present* in the data it was built from or *assigned* since, in a private flag. It also holds a reference to its owning node. The public `is_loaded` check evaluates FR-018 at read time: `present or owner is None or not owner.id`.

- `Attribute`: the private flag is set in the node's `_init_attributes` from `name in data`, and set by the `value` setter.
- `RelatedNode` (cardinality-one and hierarchical `parent`): the flag is set in `_init_relationships` from `name in data`. Assignment through `InfrahubNode.__setattr__` builds a new `RelatedNode`, which is bound as present.
- `RelationshipManager` (cardinality-many and hierarchical `children`/`ancestors`/`descendants`): presence is the existing `initialized` flag (`data is not None`, set to `True` by `fetch()`). The manager already holds its `node`.
- Peers inside a manager's list and free-standing field objects (no owner) are always loaded.
- A private `_bind(owner, present)` helper attaches the owner and flag after construction, so the public constructors keep their signatures.

**Rationale**: Rule 3 ("the node has no `id`") changes when a new node is saved and receives an id. Evaluating it at read time from `owner.id` makes FR-018's "after save" case fall out with no state transition code in `save()`, `create()` or `_process_mutation_result()`. Reusing `initialized` for managers keeps one source of truth for "the SDK has this peer list".

**Alternatives considered**:

- *Snapshot rule 3 at construction and flip flags after save.* Rejected: it needs hooks in every save path (create, upsert, update, batch) on both clients, and misses a caller assigning `node.id` by hand.
- *Store the known set on the node (`set[str]` of known field names).* Rejected: field objects are handed out and read on their own (`attr = node.name; attr.value`), so the check has to be reachable from the field.

## R2. Which reads are detected

**Decision**: Detection happens on the value-bearing accessors only:

| Field type | Detected reads | Not detected |
|---|---|---|
| `Attribute` | `value` | `id`, `is_default`, `is_from_profile`, properties (`source`, `owner`, `is_protected`, …), `is_loaded` |
| `RelatedNode` (cardinality-one) | `id`, `hfid`, `hfid_str`, `display_label`, `typename`, `kind`, `initialized`, `peer`, `get()` (and so `fetch()`, which reads `id`/`typename`) | relationship properties, `is_loaded`, `name`, `schema` |
| `RelationshipManager` (cardinality-many) | `peers`, `peer_ids`, `peer_hfids`, `peer_hfids_str`, indexing (and so iteration), `is_from_profile` | `initialized`, `has_update`, `is_loaded`, `name`, `schema` |

**Rationale**: These are exactly the accessors that return a value the SDK may never have seen. `RelatedNode.initialized` is detected because on an unknown relationship it answers "no peer" without knowing. `RelationshipManager.initialized` is not detected, because it is already the documented way to ask "has this been fetched?". Attribute properties are out of scope (Known Divergences).

**Alternatives considered**: Detecting at `node.<field>` (attribute access on the node). Rejected: FR-019's check must be reachable without triggering detection (`node.description.is_loaded`), and internal code does `getattr(node, name)` everywhere.

## R3. Keeping the SDK's own reads silent (FR-027)

**Decision**: Use a hybrid approach.

1. Inside the field classes, internal methods (`add`, `remove`, `extend`, `_generate_input_data`, `fetch` bookkeeping) use private storage (`_value`, `_peers`, `_id`, …) directly.
2. Node-level internal operations run under a context-local "internal access" flag (a `contextvars.ContextVar`, entered with a context manager and a decorator), which turns detection off for the duration. Covered operations: `_generate_input_data`, `_strip_unmodified`, `_generate_mutation_query`, `_validate_upsert`, `_process_mutation_result`, `get_path_value`, `get_human_friendly_id` (and so `hfid`, `hfid_str`, store indexing), plus CLI paths that are not plain rendering (`ctl/object/update.py` relationship application).
3. CLI rendering (`ctl/formatters/*`) and the JSON importer check `is_loaded` and skip unknown fields (FR-030), rather than reading under suppression.

**Constraint**: An internal-access region must not create asyncio tasks or call user code. A task created inside the region copies the context and would keep suppression for its whole life. The covered methods satisfy this today, and new ones must too.

**Rationale**: The node-level internals read dozens of public accessors (`rel.initialized`, `rel.id`, `attr.value`, `rel.peer`) across two client implementations. Rewriting each to private storage is a large, error-prone diff that would also duplicate logic held in the public properties (for example `RelatedNode.id` preferring `_peer.id`). A `ContextVar` is safe with asyncio, because each task has its own context, and internal operations never call back into user code. Using `is_loaded` in the CLI and importer is better than suppression there: those paths decide what to show or transfer, and should skip unknown data rather than render a blank as if it were real.

**Alternatives considered**:

- *Private accessors everywhere.* Rejected for the diff size and the duplicated logic.
- *A global (module-level) flag.* Rejected: not safe under concurrent tasks.

## R4. Warning class, message and stack level

**Decision**:

- `FieldNotLoadedWarning(FutureWarning)` lives in `infrahub_sdk.exceptions`, next to the errors. Subclassing `FutureWarning` keeps it visible under Python's default filters (FR-025). A dedicated class lets consumers opt into strictness early with `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning`.
- The message names the kind, the field and the selection, and **not** the node id, for example `InfraDevice.description was not fetched (selection: exclude=['description']). Add it to the selection before reading it.` In 1.x the warning appends `This will raise FieldNotLoadedError in infrahub-sdk 2.0.`
- `stacklevel` is computed by walking the stack to the first frame outside the `infrahub_sdk` package, so the warning points at the caller's line.

**Rationale**: Python de-duplicates warnings by `(text, category, lineno)` per module. Leaving the id out of the text means a loop over 1,000 nodes reports once per call site rather than 1,000 times. Python 3.12's `skip_file_prefixes` would do the stack walk for us, but the SDK supports 3.10.

**Alternatives considered**: `DeprecationWarning` (hidden by default inside libraries, which is exactly the visibility problem the PRD raised), and a custom `UserWarning` subclass (visible, but doesn't signal "future behaviour change").

## R5. Strictness: the switch point and the `only` exception

**Decision**: A private module-level constant, `_STRICT_FIELD_ACCESS = False`, in `infrahub_sdk/node/field_access.py` is the single switch point (FR-024). An unknown read raises `FieldNotLoadedError` when either the constant is `True` or the owning node's selection is strict (produced by `only`, FR-023); otherwise it warns. The 2.0 release flips the constant. Tests flip it with `monkeypatch`.

**Rationale**: Making it a constant, rather than a `Config` field or environment variable, honours "no configuration setting" (Out of Scope) while still giving tests and the 2.0 change one place to edit.

**Alternatives considered**: An environment variable (`INFRAHUB_STRICT_FIELD_ACCESS`). Rejected as a configuration toggle by another name. Opting in through the warnings filter (R4) already covers early adopters.

## R6. Error types

**Decision**: Three direct subclasses of `Error` in `infrahub_sdk/exceptions.py`:

- `FieldNotLoadedError`: reading a field the SDK does not know (FR-021 and FR-024). It carries `kind`, `field` and `selection` (the label, or `None` when the origin is unknown).
- `SelectionFieldNotFoundError`: a name in `only` that resolves nowhere (FR-009), or that needs fragments (FR-011). It carries `kind`, `field`, `implementing_kinds` (for FR-011).
- `SelectionConflictError`: `only` combined with `include` or `exclude` (FR-005).

**Rationale**: Constitution IV and FR-028. The names follow the module's existing `...NotFoundError` and `...Error` patterns, and `FieldNotLoadedError` matches `is_loaded`.

**Alternatives considered**: A shared `SelectionError` base for the two selection errors. Rejected: FR-028 requires *direct* subclasses of `Error`, so that no intermediate class can be caught by accident.

## R7. Selection: what is recorded and how it reaches peers

**Decision**: A frozen `Selection` dataclass in `infrahub_sdk/node/selection.py` records `only`, `include`, `exclude`, `strict` (true iff produced by `only`, directly or as a peer) and an optional `peer_of` label (`"InfraDevice.site"`). `Selection.describe()` renders the message label:

- `only=['name']`
- `include=['tags'], exclude=['description']`
- `default selection`
- For prefetched or expanded peers: `peer of InfraDevice.site, fetched with <parent label>`

`client.filters` builds the `Selection` from its arguments and binds it to every node it creates. `_process_relationships` binds a derived peer `Selection` (same `strict`, `peer_of` set) to the peer nodes it builds. Nodes created any other way (`client.create`, `InfrahubNode(...)`, `from_graphql` called directly, `convert_query_response`, the importer) have no selection, so messages report an unknown origin (FR-026).

**Rationale**: FR-026 asks for the selection only when an SDK query produced the node. Binding it in `filters` covers `get`, `all`, `filters`, batch use and hydration, because they all go through `filters`.

## R8. Validating `only`, and "before any request is sent"

**Decision**:

- `SelectionConflictError` is checked first in `get`, `all` and `filters` (and in the hydration methods), before any schema lookup or query.
- Name validation runs in `filters` after the kind's schema is resolved (the existing first step) and before the data query is generated and executed. For a generic kind, the implementing kinds' schemas come from the same schema cache (`client.schema.get` for each name in `used_by`).
- Valid names are the kind's attribute names, relationship names, hierarchical field names (when the kind supports a hierarchy), and the floor names `id`, `hfid`, `display_label` (FR-008).
- Generic rules: a name on the generic is valid. A name only on implementing kinds is valid with `fragment=True` (FR-010) and raises `SelectionFieldNotFoundError` naming fragments and the implementing kinds when `fragment=False` (FR-011). A name nowhere raises `SelectionFieldNotFoundError` (FR-009).

**Rationale**: "Before any request is sent" (FR-005, FR-009, SC-006) is read as "before the data query is sent". The schema lookup that resolves the kind already happens before query generation today, and is served from cache after the first call. Mutual exclusion needs no schema, so it is checked first.

## R9. Generating the query under `only`

**Decision**: Move the field-selection *decisions* into pure helpers on `InfrahubNodeBase` (or in `selection.py`), used by both the async and sync generators:

- An attribute is selected iff it is in `only` (when `only` is given), or not in `exclude` (otherwise).
- A relationship is selected iff it is in `only` (when given). Otherwise the existing rule applies: not excluded, and either cardinality-one, or cardinality-many of kind attribute/parent, or named in `include`.
- A peer is expanded iff `prefetch_relationships` is set, or `only` is absent and the relationship is named in `include` (today's behaviour). Under `only`, a named relationship without `prefetch_relationships` gets the floor envelope only (FR-012), and `prefetch_relationships` expands peers to their default set without adding members to the selection (FR-013).
- A hierarchical field is selected under `only` iff named. Its peer is the floor envelope unless `prefetch_relationships` is set (FR-014). Without `only`, today's rule is unchanged.
- **Generic fragments under `only`**: the generic part requests the names defined on the generic. Each implementing kind's fragment requests the remaining names that kind defines, with inherited fields included. The default path keeps its existing `exclude_child` logic.

The async and sync generators keep their own loops, because peer schemas are fetched with the client, but they call the same decision helpers.

**Rationale**: Constitution I points out that the selection rules are duplicated per client. Extracting the decisions removes the drift risk without restructuring the async/sync schema fetching. The generic-fragment rule avoids a gap in the existing `inherited=False` approach: a field an implementing kind inherits from a *different* generic would be skipped, and FR-010 would accept a name the query never requests.

## R10. Store population for floor-only peers

**Decision**: Under `only`, `_process_nodes_and_relationships` builds and stores peer nodes only when `prefetch_relationships` is set. Floor-only peers are **not** turned into nodes or stored. Their identity stays on the `RelatedNode` references.

**Rationale**: Storing floor-only peer nodes would overwrite broader nodes of the same id already in the store. In generator runs that store is shared with `convert_query_response` results, so unrelated code would start failing on reads. The reference already carries everything the floor fetched. Today's `include=[...]` path, which embeds full peers, keeps storing them.

**Store-miss hint (FR-026)**: When `RelatedNode.get()` (and so `.peer`) misses the store for a reference whose peer was never fetched, it keeps raising `NodeNotFoundError` (same type, for compatibility) with a message that names the relationship and says to call `fetch()` on it or query with `prefetch_relationships=True`. This is where users meet the reference-only result of `only=["site"]`, so this is where the hydration hint belongs.

**Consequence**: After migrating the group lookups to `only=["members"]` (FR-032), group members are no longer pushed into the store by the lookup itself. Every migrated caller either needs only `id`/`typename` (query groups) or hydrates with `members.fetch()` straight away (CLI generator and check), which populates the store with default-selection nodes as before.

## R11. `hfid` in the queried node's envelope (FR-008, FR-017)

**Decision**: Without `only`, `generate_query_data_init` keeps today's envelope (`id`, `hfid`, `display_label`, `__typename`). Under `only`, the envelope is `id`, `display_label`, `__typename`, and `hfid` is added only when named in `only`. Both peer envelopes are unchanged.

**Rationale**: `InfrahubNodeBase.hfid` is computed from attributes and never reads the envelope value, so the SDK's object model doesn't need it. But the raw payload is observable. `get_raw_graphql_data()` returns it, `infrahubctl export` writes it to `nodes.json`, and the Ansible collection's `node` module returns it to playbooks as the module result (`plugins/module_utils/node.py:37`). Dropping `hfid` from the default envelope would silently change that output for code that never opted in (critique X1). Under `only` the caller lists the fields they want, so leaving `hfid` out unless named is the opt-in behaviour. The brief's original plan (drop it everywhere) is recorded under Out of Scope as a separate change that needs consumer notice.

**Alternatives considered**:

- *Drop it from every query envelope (the brief).* Rejected for the reasons above.
- *Compute it client-side into the raw payload.* Rejected: it can't be computed when HFID components weren't fetched, and the raw payload would no longer be raw.

**Test impact**: None for default queries (SC-004: byte-identical). New selection-matrix cases cover `only` with and without `hfid`.

## R12. Peer hydration with `only` and `exclude` (FR-015, FR-016)

**Decision**:

- `RelatedNode.fetch(timeout=None, priority=None, only=None, exclude=None)` and `RelationshipManager.fetch(only=None, exclude=None)`, with identical sync counterparts. New parameters are keyword arguments appended at the end.
- Mutual exclusion is checked first.
- When `only` is given, it is validated once against the relationship's declared peer kind (`schema.peer`) using the FR-010 rule (on the generic or any implementing kind; fragments don't apply because concrete kinds are queried). Then each concrete peer kind receives `only` filtered to the names that kind defines.
- A concrete peer kind that defines none of the named fields beyond the identity floor names is not queried, and its peers stay references, because they already hold everything that query would return.
- `RelationshipManager.fetch` on an uninitialized manager re-queries the parent with `only=[name]` (FR-032), replacing `include=[name]` plus an exhaustive `exclude`.
- Peers hydrated with `only` come from `filters(only=...)`, so their nodes carry a strict selection automatically.

**Rationale**: This keeps SC-006 for hydration, and makes `only` usable on heterogeneous relationships such as group members.

## R13. Where `only` goes in the method signatures

**Decision**: Append `only: list[str] | None = None` as the **last** explicit parameter (before `**kwargs` where present) of `get`, `all` and `filters` on both clients, in every `@overload`, and as the last parameter of `generate_query_data_init`, `generate_query_data` and `generate_query_data_node`.

**Rationale**: Inserting it next to `include`/`exclude` would shift the positions of every later parameter, which is a breaking change for positional callers (constitution II). Docstrings document `only` next to `include` and `exclude`. `test_validate_method_signature` keeps the async and sync signatures identical.

## R14. What counts as "combined"

**Decision**: `only` conflicts with `include` or `exclude` when that parameter `is not None`, including an empty list.

**Rationale**: Passing both is ambiguous whatever the list contains. A list that happens to be computed down to empty is exactly the case where silently accepting it would hide a bug. Every internal caller passes `None`.

## R15. Writes to cardinality-many relationships

**Decision**: FR-020 ("assigning always succeeds") applies to attributes and cardinality-one relationships. Cardinality-many relationships keep their existing write contract: `add`, `extend` and `remove` raise `UninitializedError` until the manager is initialized (fetched, or given data at construction). This is unchanged.

**Rationale**: Adding to a peer list the SDK has never seen can't be merged correctly, which is why the guard exists. The brief puts the related `new_node.tags.add()` case out of scope. The spec's FR-020 wording should say so explicitly (to be raised in critique).

## R16. First-party consumers and call sites

**Decision**: Migrate the six call sites FR-032 lists, and also handle three more first-party readers found during research:

| Site | Change |
|---|---|
| `RelationshipManager.fetch` (async, sync) | `only=[name]` instead of `include=[name]` plus an exhaustive `exclude` |
| `ctl/generator.py` group lookup | `only=["members"]` |
| `ctl/check.py` group lookup | `only=["members"]` |
| `query_groups.py` `get_group` (async, sync) | `only=["members"]`. Members only need `id`/`typename` |
| `client.get_list_repositories` (async, sync) | Unchanged: keeps its explicit `include` with `fragment=True` (see the note below) |
| `ctl/formatters/base.py`, `ctl/formatters/yaml.py` (and table/csv/json through them) | Skip fields whose `is_loaded` is false (FR-030) |
| `ctl/object/update.py` `_apply_relationship` | Replace the peer list and mark the manager initialized, so the mutation sends the new peers even when the relationship was never fetched |
| `transfer/importer/json.py` `remove_and_store_optional_relationships` | Check `is_loaded` before `peer_ids`. Nodes built from exported default-selection GraphQL have unknown cardinality-many relationships, which are handled separately through `relationships.json` |

`client.get_list_repositories` keeps its explicit `include`, because the repository nodes it returns are public API and, under `only`, reading any of their other fields would raise `FieldNotLoadedError`.

**Rollout note (outside this repository)**: the Infrahub server, the Ansible collection and `infrahub-sync` all use this SDK. In 1.x they will log `FieldNotLoadedWarning` wherever they read fields they never fetched. Running their test suites with `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning` against this release is the cheapest way to size the 2.0 impact. This belongs in the release notes, not in this change.

## R17. Test strategy

**Decision**:

- Unit tests, mocked with `httpx_mock`, parametrised over both clients wherever behaviour is observable:
  - **Selection matrix**: `only` present, absent and empty; `include` alone; `exclude` alone; `include` with `exclude`; each forbidden combination; attributes versus relationships; cardinality-many; hierarchical; generics with and without fragments; unknown names; floor names.
  - **Access matrix**: every row of the FR-018 table, for each field type, with the switch on "warn" and on strict. Assertions cover the returned value, the warning category and exact text, the error type and its attributes, and `is_loaded`.
  - **Internal reads**: save, upsert, store and HFID on partial nodes emit no warning.
  - **Regression**: a node with a relationship-traversing HFID, fetched narrowly, stored, retrieved by id, modified and saved.
  - **SC-008**: generate an `only` query, extend the test schema with extra attributes and relationships, regenerate, and assert the two are identical.
- Add `error::infrahub_sdk.exceptions.FieldNotLoadedWarning` to `[tool.pytest.ini_options].filterwarnings`. Any unexpected unknown-field read in the SDK's own code or tests then fails the suite. Tests that exercise the warning use `pytest.warns`, which overrides the filter locally.
- Integration (testcontainers): with `only=["name"]` against a live server, returned nodes expose `name` and the floor, and reading `description` raises. Hydrating a relationship with `only` makes exactly that peer field readable.

**Rationale**: Constitution V (concrete assertions, both paths). The warnings-as-errors filter is the cheapest guard for FR-027 and stops new internal reads from slipping in.

## R18. Documentation and changelog

**Decision**:

- `docs/docs/python-sdk/guides/query_data.mdx`: add a "Selecting exactly the fields you need with `only`" section, and a "Fields that were not fetched" section covering `is_loaded`, the warning and the 2.0 plan. The second section gives the fix path (widen the selection, call `fetch()`, check `is_loaded` only where provenance is unknown). It shows how to opt into strictness early with `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning`, and notes that `getattr(..., default)` and `hasattr` no longer hide an unknown read in strict mode. Correct the `include` description (peers are expanded in full, not just initialized), the `exclude` example (`device.site` is a reference whose value is unknown, not `None`), and the cardinality-many example at lines 336-359 (`peers` warns rather than silently returning `[]`). All examples use async/sync tabs.
- Regenerate `docs/docs/python-sdk/sdk_ref/**` with `uv run invoke docs-generate`, since docstrings change.
- Changelog fragments: `+infp-532-only.added.md` (`only`, `is_loaded`, hydration selection), `+infp-532-field-access.deprecated.md` (reading unfetched fields: warns now, raises in 2.0) and `+infp-532-call-sites.changed.md` (first-party call sites now use `only`, so group lookups no longer push every member into the store; the CLI skips fields that weren't fetched).

## R19. Naming the known-state check

**Decision**: `is_loaded`.

**Rationale**: It reads naturally in the common case (`if node.description.is_loaded:`), doesn't collide with `initialized`, and matches `FieldNotLoadedError`. For an unsaved node the value is "loaded" in the sense that the SDK holds it, even though nothing was fetched. That reading is documented.

**Alternatives considered**: `is_known` (precise, but unusual in Python APIs), `is_fetched` (wrong for unsaved nodes) and `has_value` (confusable with "is not None").
