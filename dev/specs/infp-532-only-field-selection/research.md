# Research: Fetch Only the Named Fields with `only`

**Feature**: INFP-532 | **Date**: 2026-10-14 | **Spec**: [spec.md](./spec.md)

The requirements are fixed by the idea brief (see the spec's Input line). This document records how the SDK code works today and the design decisions that follow from it. References are to the tree at `13af0d22` (`origin/infrahub-develop`).

The prototype branch `field-selection-only-infp-532` was read for the problems it ran into. Its design is not adopted where the brief differs; R17 lists the differences.

## How the SDK builds queries and nodes today

- **Query methods**: `get` (`infrahub_sdk/client.py:758`), `all` (`:1143`) and `filters` (`:1258`) on `InfrahubClient`, with the same signatures on `InfrahubClientSync` (`:3434`, `:2988`, `:3144`). `get` builds a filter dictionary and calls `filters`; `all` calls `filters` with `query_name=f"All_{kind}"`. Each method has overloads: 6 for `get`, 2 for `all` and 2 for `filters`, per client.
- **Query generation**: `filters` calls `InfrahubNode(...).generate_query_data(...)` (`client.py:1319`, sync `:3205`). In `infrahub_sdk/node/node.py`:
  - `generate_query_data_init` (`:654`) requests `id`, `hfid`, `display_label` and `__typename` for the queried node.
  - `generate_query_data_node` (`:1453`, sync `:2680`) adds every attribute that is not excluded. It adds every cardinality-one relationship, and every cardinality-many relationship of kind Attribute or Parent or named in `include`.
  - Each peer is requested as `id`, `hfid`, `display_label`, `__typename` (`related_node.py:298`, `relationship.py:141`).
  - With `prefetch_relationships=True`, or when `include` names the relationship, the peer gets its default fields as well (`node.py:1514-1521`).
- **Hierarchy fields**: `_process_hierarchical_fields` (`node.py:1307`, sync `:2535`) adds `parent`, `children`, `ancestors` and `descendants` when the kind has a hierarchy and the name is in `include` or `prefetch_relationships` is set.
- **Generic kinds**: without `fragment=True`, only the generic's own fields are requested. With `fragment=True`, each kind in `used_by` gets an `...on Kind` block with aliased field names (`node.py:1425-1449`). That loop calls `client.schema.get(kind=child)` without `branch`.
- **Building nodes**: `InfrahubNodeBase.__init__` (`node.py:91`) keeps `id`, `display_label` and `__typename` from the response and discards the node's server `hfid`.
  - `_init_attributes` (`:271`) creates an `Attribute` for every schema attribute, from `data.get(name)`. A field the server did not return and a field whose value is null both end up as `value=None`.
  - `_init_relationships` (`:901`) creates a `RelatedNode` or `RelationshipManager` with `data=None` for a missing relationship. `RelationshipManager.initialized` is `data is not None`.
- **Peers in the store**: `_process_nodes_and_relationships` (`client.py:826`) builds peer nodes with `_process_relationships` (`node.py:1803`) when `prefetch_relationships` is set or `include` names any relationship.
  - In that case it builds a node for the peer of every cardinality-one relationship in the response, even one requested as a reference only.
  - `filters` puts the nodes and these peers in the store when `populate_store` is on (`client.py:1404-1411`).
- **HFID**: `get_human_friendly_id` (`node.py:196`) reads each path of the schema's `human_friendly_id` through `get_path_value` (`:141`). For a path through a relationship, such as `location__name__value`, it finds the peer with `RelatedNode.get()`: first the peer cached on the relationship, then the store.
  - `_process_relationships` does not set the cached peer, so the peer must be in the store.
- **Saving**: an attribute that was never set and has the value `None` produces an empty payload and is not sent (`attribute.py:157-159`). A relationship that is not initialized is skipped (`node.py:474-484`). Saving therefore already leaves unfetched fields alone.
- **Errors**: `infrahub_sdk/exceptions/` is a package.
  - Client-side errors live in `base.py`.
  - `catalogue.py` is generated and must not be edited.
  - `tests/unit/sdk/test_exceptions.py:105-119` requires every exported error to have exactly one base class.
  - `tests/unit/sdk/test_exceptions_public_names.py` requires every exported error to descend from `Error` and to be listed in `tests/fixtures/error_catalogue/public_names.json`.
- **Tests**: query-generation tests in `tests/unit/sdk/test_node.py` compare the whole generated query with `==`, for example `test_query_data_include` (`:1283`) and `test_query_data_exclude` (`:1403`). Both clients are covered with `@pytest.mark.parametrize("client_type", client_types)`.

## R1. Where `only` goes in the signatures

- **Decision**: add `only: list[str] | None = None` as the last named parameter of `get`, `all` and `filters` on both clients, in every overload and in the implementation. In `get` and `filters` it goes before `**kwargs`. The public `generate_query_data_init`, `generate_query_data` and `generate_query_data_node` do not change. The query for `only` is built by new private methods on both node classes, which `filters` calls when `only` is not `None`.
- **Rationale**: callers that pass arguments by position keep working (constitution II). `test_validate_method_signature` (`tests/unit/sdk/test_client.py:138`) checks that the async and sync implementations match; `docs-validate` checks the overloads through the generated reference. Keeping the public generators unchanged avoids a second public way to use `only` that would skip the name check, and leaves the default path untouched (SC-003).
- **Alternatives considered**:
  - Placing `only` next to `include` and `exclude` reads better, but would shift every later parameter for positional callers. Rejected.
  - Adding `only` to the public `generate_query_data*` methods. Rejected (critique E10): the brief does not ask for it, and those methods do not check names.

## R2. Combining `only` with `include` or `exclude` (FR-009)

- **Decision**: raise `FieldSelectionConflictError` when `only is not None` and either `include is not None` or `exclude is not None`, including empty lists. The check is the first statement of `get`, `all` and `filters`, before the schema lookup, so no request is sent.
- **Rationale**: FR-009 says "before any request". `get` reads the schema before calling `filters` (`client.py:780-798`), so the check cannot wait until `filters`. An empty list is still a choice the caller made; accepting it would hide a list that was computed down to empty by mistake.
- **Alternatives considered**: treating an empty `include` or `exclude` as not passed. Rejected for that reason.

## R3. Checking the names in `only` (FR-008)

- **Decision**: `filters` checks the names after it resolves the kind's schema and before it generates the data query. A name is accepted when it is:
  - an attribute or relationship of the kind;
  - for a generic kind, an attribute or relationship of the generic or of any kind in `used_by`;
  - `parent`, `children`, `ancestors` or `descendants`, when the kind has a hierarchy;
  - `id`, `display_label` or `hfid`.
- Every other name raises `FieldNotFoundError`, naming the field and the kind. Implementing kinds' schemas come from the client's schema cache for the same branch (`client.schema.get(kind=..., branch=branch)`), which holds the whole branch after the first lookup.
- **Rationale**: FR-008 asks for the error before the data query is sent. The schema lookup already happens before query generation and is cached, so checking there adds no request in the usual case. `ancestors` and `descendants` are not in `relationship_names`, so they need their own rule.
- **Alternatives considered**: checking inside `generate_query_data`. Rejected: that method is public and is also used without a client request, and the checks for a generic kind need the client's schema cache.

## R4. The query under `only` (FR-002, FR-003, FR-004, FR-006, FR-007)

- **Decision**:
  - The queried node requests `id`, `display_label` and `__typename`. It requests the server's `hfid` only when `only` names `hfid` (R5).
  - An attribute is requested only when named. A relationship of any cardinality and kind is requested only when named, as a reference (`id`, `hfid`, `display_label`, `__typename`).
  - With `prefetch_relationships=True`, a named relationship's peer also gets its default fields, as today (`peer_node.generate_query_data_node(property, include_metadata)`). Relationships that are not named are not requested.
  - `parent`, `children`, `ancestors` and `descendants` are requested only when named. Without `prefetch_relationships` they are references. With it, they get the same peer fields today's prefetch requests for them: the hierarchy generic's default fields, without the four hierarchy names, inside `...on <hierarchy generic>` (`_process_hierarchical_fields`, `node.py:1307-1356`). Under `only`, `parent` and `children` come from one place only (`_process_hierarchical_fields`), so the relationship loop does not add them a second time.
  - `only=[]` requests `id`, `display_label` and `__typename` only.
  - `only=None` takes the existing code path unchanged.
  - For a generic kind, a name that the generic has is requested on the generic. A name that only some implementing kinds have is requested in an `...on Kind` block for each of those kinds, under the existing alias form `__alias__Kind__name`, whether or not `fragment=True` is set. The existing fragment loop in `generate_query_data` (`node.py:1425-1449`) is not run under `only`, because it would add each implementing kind's default fields.
- **FR-004 and FR-006**: hierarchy fields named in `only` follow FR-003 and FR-004 like any other named relationship. FR-006 says only that they are fetched when named. The plan first read FR-006's "as references" literally; the owner chose this reading on 2026-10-14 (critique P3), because today's prefetch already returns these fields with their default fields.
- **`property=True` and `include_metadata=True`**: they keep working under `only` and apply to the named fields and to the node. Confirmed by the owner on 2026-10-14. They add data about the fields the developer named, not more fields of the kind, and the developer asks for them explicitly. FR-001's "nothing else" is read as "no other fields of the kind".
- **Unchanged under `only`**: filters, `order`, `partial_match`, `offset`, `limit` and `count`.
- **Rationale**: this follows FR-002 to FR-007 directly. Keeping the `only=None` path unchanged is what SC-003 needs, and it is checked by leaving every existing query-generation test unedited.

## R5. `hfid` in `only` (FR-005)

- **Decision**: `id` and `display_label` are always requested, so naming them adds nothing. `hfid` requests the server's `hfid` field on the queried node, in the place the default query puts it (after `id`), and nothing else: no field, relationship or peer that the HFID is made of.
  - For a generic kind, `hfid` is requested on the generic part of the query when the generic or any kind in `used_by` has an HFID.
  - For a kind with no HFID, naming `hfid` adds nothing.
- **Reading it**: a node from a query with `only` keeps the `hfid` that its response contained in a private attribute, set when the node gets its marker (R7). `hfid`, `hfid_str`, `get_human_friendly_id()` and `get_human_friendly_id_as_string()` return that value, or `None` when it is empty or null, and the store indexes the node by it. A node from `only` whose response did not contain `hfid` calculates its HFID from the fields it fetched (R8).
- **Nodes that keep calculating their HFID**: nodes not from `only`, and peers built for a node from `only` (R9), never get the private attribute. Their HFID is calculated as before, even though the response contains a server `hfid` for them (in the default query and in every peer reference).
- **Rationale**: since Infrahub 1.5.0, the server stores each node's HFID as an attribute, computed when the node is written (commit [`d30588206c`](https://github.com/opsmill/infrahub/commit/d30588206c), "IFC-1812 Refactor HFID & display_labels"). When a query requests `hfid`, the server adds `human_friendly_id` to the attributes it loads with the node ([`resolver.py:254`](https://github.com/opsmill/infrahub/blob/infrahub-v1.11.7/backend/infrahub/graphql/resolvers/resolver.py#L254) in Infrahub 1.11.7), and `Node.get_hfid()` returns the stored value; it calculates the value only when none is stored ([`core/node/__init__.py:231`](https://github.com/opsmill/infrahub/blob/infrahub-v1.11.7/backend/infrahub/core/node/__init__.py#L231)). Requesting the parts of the HFID instead makes the server follow each relationship that a part goes through, and read the peer's attribute plus the peer's own `hfid` and `display_label`. That costs more than reading the stored value, which works against the purpose of `only`. The owner chose the stored value on 2026-10-16 ([review thread](https://github.com/opsmill/infrahub-sdk-python/pull/1423#discussion_r4294381206)).
- **Alternatives considered**:
  - Replacing `hfid` with the fields of the kind's `human_friendly_id`, with one peer attribute for a part that goes through a relationship, and keeping those peers in a private slot on the node so that `node.hfid` did not depend on the store. This was the first design and was implemented. The owner replaced it on 2026-10-16 for the cost described above.
  - Reading the server's `hfid` on every node. Rejected: it would change `node.hfid` for nodes not from `only` (SC-003, constitution II).

## R6. Recording which fields the response contained (FR-011)

- **Decision**: every field object records, in a private flag, whether the data its node was built from contained the field. This applies to every node, not only to nodes from `only`.
  - `Attribute`: `_init_attributes` passes `name in data`. The `value` setter sets the flag.
  - `RelatedNode` (including `parent`): `_init_relationships` passes `name in data`. Assigning `node.site = ...` builds a new `RelatedNode`, which is marked as assigned. `{"node": null}` in the response counts as contained.
  - `RelationshipManager` (including `children`, `ancestors` and `descendants`): uses the existing `initialized` flag, which `fetch()` sets. The `peers` setter also marks the manager as loaded.
- Each field object gets a private reference to its node, bound after construction so that the public constructors keep their signatures. `is_loaded` returns `True` when the flag is set, when the field has no node, or when the node has no `id`, and `False` otherwise. It never raises.
- **Which objects are bound**:
  - every `Attribute`, `RelatedNode` and `RelationshipManager` that `_init_attributes` and `_init_relationships` create;
  - for hierarchical kinds, both places that hold `parent` and `children` (the relationship and `_hierarchical_data`);
  - the `RelatedNode` that `InfrahubNode.__setattr__` builds when a relationship is assigned, which is marked as assigned.
- The `RelatedNode` objects inside a `RelationshipManager`'s list are not bound, so they are always loaded.
- **Reference to the node**: a plain reference, as `RelationshipManager.node` already is (`relationship.py:198`). A weak reference was considered (critique E12) and rejected: it would make `is_loaded` and the raising depend on whether the developer still holds the node, and the reference cycle already exists for relationship managers.
- **Rationale**: FR-011 asks for `is_loaded` on any node, including after `exclude` and after saving a new node. Checking the node's `id` when `is_loaded` is read covers the "after a new node is saved" edge case with no change to the save code. Field objects are handed out on their own (`attr = node.name`), so the check has to be reachable from the field.
- **Alternatives considered**:
  - Recording the flag only for nodes from `only`, as the code map suggested. Rejected: FR-011 applies to every node.
  - Keeping a set of field names on the node. Rejected for the reason above.
- **Note**: for nodes not from `only`, `is_loaded` can now be `False` (for example after `exclude`), and nothing else changes for them.

## R7. Raising `FieldNotLoadedError` (FR-010)

- **Decision**: a node built by a query with `only` carries a private marker: the `only` list and, for a peer, the relationship it was returned through (for example `InfraDevice.site`). The accessors in the contract's table raise `FieldNotLoadedError` when the field is not loaded and its node carries the marker. On every other node they return what they return today.
- The marker is set by `_process_nodes_and_relationships` on the nodes it builds and on the peers it builds from the same response (R9). Peers fetched with `fetch(only=...)` come from `filters` and get their own marker.
- **Message**: names the kind, the field and the `only` list, for example `InfraDevice.description was not fetched: the node was queried with only=['name']. Add 'description' to only, or check is_loaded before reading it.` For a peer it also names the relationship: `... the node is a peer of InfraDevice.site, queried with only=['site']`.
- **Which reads raise**: the contract lists every accessor. In short:
  - attributes raise on `value` only;
  - cardinality-one relationships raise on the peer and its identifiers, and on `fetch()`;
  - cardinality-many relationships raise on the peer list and everything derived from it.
- **What never raises**: `is_loaded`, `initialized`, `has_update`, `name`, `schema`, and the properties of attributes and relationships (`source`, `owner`, `is_protected` and similar).
- **Rationale**: FR-010 limits raising to nodes from `only` and the peers returned with them. The brief puts the warning for all other nodes out of scope. `RelatedNode.initialized` and `RelationshipManager.initialized` are how the SDK itself decides what to save (`node.py:474-484`, `:576-613`), so they must not raise.

## R8. The SDK's own reads must not raise (FR-010)

- **Decision**: the error is raised only by the public accessors and only for a field that is not loaded, so SDK code that reads loaded fields is unaffected. The SDK code that can touch unloaded fields during saving, upserting, HFID calculation and storing reads private storage instead:
  - `Attribute._initialize_graphql_payload`, `is_from_pool_attribute` and `is_unresolved_pool_attribute` read `_value` (`attribute.py:151-177`, `:233-248`). `_process_mutation_result` calls `is_from_pool_attribute` on every attribute (`node.py:1607`).
  - `RelatedNode.initialized` reads the cached peer, `_id` and `_hfid` (`related_node.py:190`). `_generate_input_data` and `_strip_unmodified` call it on every relationship (`node.py:474`, `:583`).
  - `RelationshipManager` methods (`add`, `extend`, `remove`, `fetch`, `_generate_input_data`, `is_from_profile`) read `_peers`. `peers` becomes a property backed by `_peers`.
  - `get_human_friendly_id` uses a private version of `get_path_value` that treats a field that is not loaded as missing (`None`). It finds the peer without raising, through the cached peer and the store. A node from `only` whose response contained `hfid` returns that value instead (R5). `store.set` (`store.py:56`), `hfid`, `hfid_str` and `_generate_input_data` all go through `get_human_friendly_id`.
- **Conditions for this list to stay complete** (critique E5):
  - `RelatedNode.initialized` keeps using the peer's calculated HFID when a peer is cached, which goes through the non-raising calculation.
  - `RelationshipManager.__init__` and every internal write use `_peers`, not `peers` (`relationship.py:58`, `:209`, `:217`).
  - The `peers` getter returns the stored list itself, not a copy, because callers change it in place (for example `infrahub_sdk/ctl/object/update.py`).
  - No `__len__` or `__bool__` is added to the field classes. The SDK tests field objects for truth (`node.py:166`, `:580`, `:1805`, `:1822`), and a raising `__len__` would break that.
- The public `get_path_value` keeps reading through the public accessors, so on a node from `only` it raises for a field that is not loaded. That is a read by the developer.
- A test matrix covers the operations FR-010 names, on a node from `only` whose fields are all unfetched, on both clients: `save()` for create and update, `create(allow_upsert=True)`, `hfid`, `store.set` and the mutation-result processing.
- **Rationale**: the error cannot also be an `AttributeError` (one base class per error, see the baseline), so `getattr(x, "value", None)` does not catch it. The list of affected reads is short because only unloaded fields raise.
- **Alternatives considered**: a context variable that switches raising off during SDK operations, as in the prototype. Rejected: it hides which code reads what, it needs care with `asyncio` tasks created inside the switched-off region, and the explicit list is short.

## R9. Building peer nodes under `only`

- **Decision**: under `only`, `_process_nodes_and_relationships` builds and stores peer nodes only for relationships named in `only`, when `prefetch_relationships=True`. For hierarchy fields this is what today's prefetch builds: peer nodes for `parent` and `children`, which are schema relationships. The peers of `ancestors` and `descendants` stay on the relationship and are not built as nodes, as today.
- Under `only`, the peers are read from the node's data with the `__alias__Kind__` prefixes removed (the node's `_data` after `_strip_alias`, `node.py:616`). Today `_process_relationships` reads the raw response (`node.py:1806`, `:1823`), so the peers of a relationship that only an implementing kind has would never be built (critique E1).
- `_process_relationships` gets a private argument with the relationship names to process. Without `only`, the existing condition and loop are unchanged.
- **Rationale**: today, when `include` names any relationship, every cardinality-one peer in the response is built as a node, even one requested as a reference only, and stored with every attribute `None`. Under `only` this would replace fuller copies in the store with empty ones. It would also break the edge case where `device.site.peer` raises `NodeNotFoundError` when the site is not in the store.

## R10. `fetch(only=...)` on relationships (FR-012)

- **Decision**:
  - `RelatedNode.fetch(timeout=None, priority=None, only=None)` and `RelatedNodeSync.fetch(...)` pass `only` to `client.get(kind=self.typename, id=self.id, ...)`. `client.get` checks the names against the peer's kind before the data query is sent.
  - `fetch()` on a cardinality-one relationship that is not loaded, on a node from `only`, raises `FieldNotLoadedError`, because the peer's `id` and kind are unknown. On other nodes it keeps raising `Error` as today (`related_node.py:367`).
  - `RelationshipManager.fetch(only=None)` and `RelationshipManagerSync.fetch(only=None)`, in this order:
    1. When `only` is given, check its names against the relationship's declared peer kind (`self.schema.peer`) with the rule of R3 (for a generic peer kind: the generic or any implementing kind). This runs before any request, so a misspelt name never sends a query (SC-004, critique E3).
    2. When the manager is not loaded, reload the relationship. On a node from `only`, the reload is `client.get(kind=..., id=..., only=[self.schema.name], populate_store=False)`. That works for `ancestors` and `descendants` as well, which the existing `include`/`exclude` reload cannot handle (`relationship.py:245-246` raise `ValueError` because those names are not in `relationship_names`, critique E2). With `populate_store=False`, the reloaded copy of the node does not replace the developer's node in the store. On any other node, the existing reload runs unchanged.
    3. When `only` is given, check its names against every distinct peer kind in the loaded list. Any name missing on any of those kinds raises `FieldNotFoundError` before any peer query is added to the batch.
    4. Add one `filters(kind=..., ids=..., only=only, ...)` per peer kind to the batch, as today.
  - Peers fetched this way go to the store and carry the `only` marker (R7).
  - **`RelatedNode.hfid` after `fetch(only=...)`**: `fetch` keeps setting the cached peer, as today (`related_node.py:369-371`). When the cached peer is a node from `only` and has no HFID, because its response did not contain `hfid` (or contained an empty value) and the fields it carries do not give one, `RelatedNode.hfid` and `hfid_str` return the HFID the reference carried from the server. So `device.site.hfid` keeps its value after `device.site.fetch(only=["description"])` (critique P4). For a cached peer that is not from `only`, `hfid` is unchanged. Confirmed by the owner on 2026-10-14: this concerns the relationship's `hfid`, not the excluded fallback for `node.hfid`.
- **Rationale**: FR-012 requires every name on every peer kind, checked before the peer queries are sent. The batch sends queries concurrently, so the check has to run before any query is added. `fetch()` on a manager is how a developer loads a cardinality-many relationship, so it must work on a manager that is not loaded, including `ancestors` and `descendants`, which FR-006 leaves unloaded unless named.
- **Alternatives considered**: not setting the cached peer under `only`, so `.peer` reads the store. Rejected: `.peer` would then depend on what the store holds.
- **Not changed**: on nodes not from `only`, the reload keeps using `include` and `exclude`, as today, including its existing failure on `ancestors` and `descendants`.

## R11. Error types

- **Decision**: three new classes in `infrahub_sdk/exceptions/base.py`, each with `Error` as its only base class:
  - `FieldNotLoadedError(kind, field, only, peer_of=None)`: reading a field that a node from `only` does not carry.
  - `FieldNotFoundError(kind, field)`: a name in `only` that is not a field of the kind.
  - `FieldSelectionConflictError()`: `only` combined with `include` or `exclude`.
- Each class keeps its arguments as attributes and builds its message the way `FragmentNotFoundError` does (`base.py:408`). Each is added to `base.__all__`, `exceptions/__init__.py` and `tests/fixtures/error_catalogue/public_names.json`. None of the names exists in the generated `catalogue.py`.
- **Rationale**: constitution IV asks for a specific subclass for each new failure. The SDK's tests allow one base class only, so the new errors cannot also subclass `AttributeError` or `ValueError`. Today a name in both `include` and `exclude` raises a plain `ValueError` (`node.py:712-715`). That stays, and the new errors follow constitution IV instead.

## R12. Typed surface

- **Decision**: add `is_loaded` to the `Attribute` and `RelatedNodeBase` protocols in `infrahub_sdk/protocols_base.py`. `infrahub_sdk/protocols.py` is generated and is not edited.
- **Rationale**: generated protocols type attributes with the `protocols_base` attribute protocols (`String`, `StringOptional` and so on, all based on `Attribute`), so `node.description.is_loaded` needs `is_loaded` on `Attribute`. They type relationships with `RelationshipAttribute`, whose access on a node returns the concrete `RelatedNode` (`related_node.py:527-553`), and with the concrete `RelationshipManager` (`protocols.py:10-14`). Both classes get `is_loaded` directly. Adding it to `RelatedNodeBase` keeps that protocol in line with the class it describes.

## R13. File objects

- **Decision**: `matches_local_checksum`, `download_file(skip_if_unchanged=True)` and `upload_if_changed` read `checksum.value` through the public accessor (`node.py:1109`, `:1145`, and `upload_if_changed`). On a node from `only` that did not fetch `checksum`, they raise `FieldNotLoadedError`. `save()` itself does not read `checksum`.
- **Rationale**: these methods compare a local file with the server checksum. When the checksum was not fetched, they cannot compare, and uploading anyway would hide the missing field and cost a full upload. FR-010 covers `save()`, which does not read the checksum. Confirmed by the owner on 2026-10-14.
- **Alternatives considered**: treating a checksum that was not fetched as "no server checksum", as the prototype did. Rejected for the reason above.

## R14. Schema lookups for implementing kinds

- **Decision**: under `only`, the schema of each kind in `used_by` is read with the query's `branch`. The existing fragment loop without `only` keeps its current call (`node.py:1427`).
- **Rationale**: on a branch where an implementing kind gained a field, the check in R3 and the query must agree. Changing the existing loop would change existing queries, which SC-003 forbids.

## R15. Test strategy

- **Unit tests** cover both clients through `client_type` parametrisation and use dataclass cases (`.agents/rules/python-testing.md`):
  - Query generation under `only`, comparing the whole generated query: attributes, cardinality-one and cardinality-many relationships, `prefetch_relationships`, `hfid` (a kind with an HFID, a generic kind without one whose implementing kind has one, a kind with no HFID, merged with named fields and with `prefetch_relationships`), hierarchy fields, generic kinds, `only=[]`, `id` and `display_label`. Existing fixtures: `schema_with_hfid` (`tests/unit/sdk/conftest.py:229`), `hierarchical_schema` (`tests/unit/sdk/test_hierarchical_nodes.py:19`), `mock_schema_query_02`, `location_schema`, `device_schema`.
  - SC-002: the same `only` call before and after adding an attribute and a relationship to the schema gives the same query.
  - SC-003: no existing query-generation test is edited. They must pass unchanged.
  - SC-004 and FR-009: the errors are raised and `httpx_mock` records no GraphQL request.
  - SC-005: the accessor table, on nodes from `only`, on peers returned with them and on peers from `fetch(only=...)`: each listed read raises when not loaded, and `is_loaded` is `False` in exactly those cases. On a default node the same reads return what they return today.
  - FR-010: the internal-operations matrix from R8.
  - FR-012: `fetch(only=...)` on cardinality-one and cardinality-many relationships, including mixed peer kinds with a name missing on one kind, a misspelt name on a manager that is not loaded (no request sent), and `ancestors.fetch(only=...)` and `descendants.fetch(only=...)` on a node from `only` where they are not loaded.
  - Generic kinds: a relationship that only an implementing kind has, named in `only` with `prefetch_relationships=True`, gives a peer node in the store.
  - HFID:
    - `node.hfid` from `only=["hfid"]` is the server's value, also over fetched fields that would give another value, and `None` for an empty or null value;
    - with `populate_store=True` and `populate_store=False`, and no peer is stored for it;
    - `client.store.get(key=node.hfid, kind=...)` returns the node from `only`;
    - without `hfid` in `only`, `node.hfid` is calculated from the fetched fields;
    - a node from a default query keeps the calculated HFID when the response's `hfid` differs;
    - `device.site.hfid` is unchanged after `device.site.fetch(only=["description"])`, and after `device.site.fetch(only=["hfid"])` when the server returns a null `hfid`.
  - Hierarchy fields named in `only`: references without `prefetch_relationships`; with it, the hierarchy generic's default fields, peer nodes built and stored for `parent` and `children` only, and no other hierarchy field added.
  - `fragment=True` with `only` adds no default fields of implementing kinds.
  - Error classes: messages and registration (the existing public-name tests pick them up).
- **Integration tests**, one per client, on `SchemaAnimal` (`infrahub_sdk/testing/schemas/animal.py`): a generic kind, and `only=["hfid"]` on an implementing kind with its own HFID (`Cat`), whose three parts include one through a relationship (`owner__name__value`) and come from the server.

## R16. Documentation and changelog

- **Decision**:
  - Add a section on `only` to `docs/docs/python-sdk/guides/query_data.mdx`, after "Excluding attribute and relationships". It covers `only`, `is_loaded`, `FieldNotLoadedError`, `hfid` in `only` and `fetch(only=...)` under "Fetching relationships manually". It makes no claim about what `include` returns for peers.
  - Add one sentence to `docs/docs/python-sdk/guides/store.mdx` saying that a node from `only` replaces a fuller copy of the same node in the store, and that `is_loaded` tells which fields it carries.
  - Update the `Raises:` sections of the docstrings that change behaviour before running `docs-generate`: `get_path_value`, `get_flat_value`, `matches_local_checksum`, `download_file`, `upload_if_changed`, and both `fetch` methods on both relationship classes.
  - Run `uv run invoke docs-generate` and commit the regenerated reference pages.
  - Add `changelog/+only-field-selection.added.md`.
- **Rationale**: constitution VII; the brief puts the correction of the `include` section out of scope.

## R17. Scope compared with the prototype

The prototype changes 58 files. This plan keeps to the brief.

| Area | Prototype | This plan |
|---|---|---|
| Reading an unfetched field on any other node | Warning in 1.x, private switch for errors in 2.0 | No change (out of scope) |
| `hfid` in `only` | Adds the server `hfid` to the query | Adds the server `hfid` to the query (FR-005, R5) |
| Names that exist only on implementing kinds | Need `fragment=True` | Accepted without it (FR-008) |
| `fetch(only=...)` on mixed peer kinds | Filters `only` per kind and skips kinds without the names | Raises unless every kind has every name (FR-012) |
| `fetch(exclude=...)` | Added | Out of scope |
| SDK's own queries (`query_groups.py`, `ctl/generator.py`, `ctl/check.py`) | Moved to `only` | Not changed |
| CLI formatters and JSON importer | Skip unfetched fields | Not changed |
| `infrahubctl object update --set` fix | Included | Separate pull request (follow-up) |
| Keeping the SDK's own reads from raising | Context variable | Private reads at the listed places (R8) |

Files outside `infrahub_sdk/client.py`, `infrahub_sdk/node/`, `infrahub_sdk/exceptions/`, `infrahub_sdk/protocols_base.py`, tests, docs and the changelog are not changed. In particular, `infrahub_sdk/ctl/`, `infrahub_sdk/transfer/` and `infrahub_sdk/query_groups.py` are not changed.
