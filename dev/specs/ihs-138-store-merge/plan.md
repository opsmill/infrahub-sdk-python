# IHS-138 - Merge nodes in the client store instead of overwriting

- **Ticket:** [IHS-138](https://opsmill.atlassian.net/browse/IHS-138) (GitHub [#413](https://github.com/opsmill/infrahub-sdk-python/issues/413))
- **Priority:** High
- **Affected versions:** observed on SDK 1.12.1
- **Target version:** SDK 1.23.0 (ships alongside Infrahub 1.11.0)
- **Status:** implemented (2026-07-02); hardened after code review (2026-07-04, section 13)

> The SDK is versioned independently of Infrahub core. 1.23.0 is a semver *minor*
> bump even though it rides the Infrahub 1.11.0 release. Because it changes
> default store behaviour (see sections 3 and 10), shipping it as a minor depends
> on two things being true: the change is framed as a bug fix, and an explicit
> opt-out exists. Both are required deliverables, not nice-to-haves.

## 1. Problem

Querying the same Infrahub node more than once can silently drop information
that was previously held in the client store.

Reproduction from the ticket:

```python
client = InfrahubClientSync(address="https://demo.infrahub.app/")

interface = client.get("InfraInterface", device__name__value="jfk1-edge1",
                       name__value="Ethernet6", prefetch_relationships=True)
client.store.get(interface.id).device.id          # works

client.all("InfraCircuitEndpoint", prefetch_relationships=True)
client.store.get(interface.id).device.id          # AttributeError: 'NoneType' has no attribute 'id'
```

The first query stores the interface with its `device` relationship. The second
query re-fetches the same interface as a *related node* of each circuit endpoint,
at a depth that does not include the interface's `device`. After the second query
the device link is gone, and the interface is present in the store twice.

## 2. Root cause

The store keys objects by a random per-object id, not by their stable UUID.

- `infrahub_sdk/node/node.py:110` - every node object gets a fresh
  `self._internal_id = generate_short_id()` on construction.
- `infrahub_sdk/store.py:47-60` - `NodeStoreBranch.set()` stores under
  `self._objs[node._internal_id]` and points `self._uuids[node.id]` /
  `self._hfids[...]` at that random id.
- `infrahub_sdk/client.py:1161-1168` - the query paths unconditionally call
  `self.store.set(node=node)` for every node and related node, with no check for
  whether the UUID is already present.

So a second fetch of the same UUID:

1. creates a new Python object with a new `_internal_id`,
2. leaves a duplicate entry in `_objs` (unbounded growth),
3. overwrites `_uuids[node.id]` to point at the newest, possibly poorer copy.

`store.get(uuid)` then resolves to the poorer copy, whose relationship was never
initialized -> `AttributeError`.

## 3. Design

Replace "last write wins, keyed by a random id" with "merge into the existing
object, keyed by UUID, field by field." A field is only overwritten when the new
fetch actually carried it; fields the new fetch did not request are left intact.

The decision of whether the new fetch carried a field requires a per-field
"was this present in the response" signal. The state of that signal across the
field types is **not uniform today**, and getting it uniform is the heart of the
fix:

- **Cardinality-many relationships** (`RelationshipManager`, including the
  hierarchical `children` / `ancestors` / `descendants`) already have a correct
  signal: `initialized = (data is not None)` (`relationship.py:202`). This genuinely
  means "was fetched." Usable as-is.
- **Cardinality-one relationships** (`RelatedNode`, including the hierarchical
  `parent` and every normal one-relationship) have a *misleading* signal:
  `initialized = bool(self.id) or bool(self.hfid)` (`related_node.py:189`) means
  "has a peer," NOT "was fetched." A fetched-but-empty one-relationship (node moved
  to root, optional relationship cleared) reports `initialized == False` and is
  indistinguishable from "not fetched." Using it as the merge gate would keep a
  stale parent after a move-to-root. **We must add a real presence flag to
  `RelatedNode`** (set from key-presence in `_init_relationships`) and gate the
  merge on that, not on `initialized`.
- **Attributes** have no signal at all. `_init_attributes` (`node.py:269`) builds an
  `Attribute` for every schema attribute regardless of the query, and a field absent
  from the response collapses to `_value = None` (`attribute.py:88-99`),
  indistinguishable from "fetched and genuinely null." We add the flag.

**Unifying principle:** every field type - attribute, cardinality-one,
cardinality-many, hierarchical - must carry a "present in this response" flag, and
the merge replaces present fields (even to empty / None) and keeps absent ones.
This is what makes moves, clears, and partial fetches all behave the way a user
reads them: *the store reflects the latest server state for whatever you actually
re-fetched, and leaves everything else untouched.*

### Merge rule (per field)

```text
for each field on the incoming node:
    if field was present in this response (initialized):
        if the stored field was locally mutated by the user (unsaved):
            keep the local value      # local edits win
        else:
            take the incoming value   # refresh, even to None
    else:
        keep the stored value         # not queried -> no fresher info
```

- Within a fetched cardinality-many relationship, the member list is *replaced*,
  never unioned, so a peer removed on the server is correctly dropped.
- For attributes, merge **field-by-field into the existing `Attribute`**, not by
  swapping the whole object (grill 4, 2026-07-02). An attribute carries more than a
  value - properties (`source`, `owner`, `is_protected`, `is_visible`) and metadata
  (`is_default`, `is_from_profile`). A query can fetch the value without the
  properties; a blind object-swap would then null previously-fetched properties -
  the same silent-loss bug one level down. Rule: overwrite the value when the
  attribute is fetched; overwrite each property/metadata sub-field only when the
  re-fetch actually included it, otherwise keep the stored one. The same applies to
  relationship properties and `node_metadata`.

### "Field" means all three relationship buckets *and* node-level scalars

A node holds relationships in **three** separate containers, and the merge must
iterate all of them or it reintroduces the bug on the ones it skips:

- `_relationship_cardinality_one_data` (`RelatedNode`)
- `_relationship_cardinality_many_data` (`RelationshipManager`)
- `_hierarchical_data` (parent / children / ancestors / descendants)

Note `self._relationships` (`node.py:117`) lists **only** `schema.relationships`,
so it does *not* include the hierarchical bucket. Do not drive the merge off
`self._relationships` alone.

It must **also** cover node-level scalars set directly in `__init__` - `display_label`
and `typename` (`node.py:113-114`) - which live on neither `_attribute_data` nor a
relationship bucket (grill 1, 2026-07-02). They are gated on presence like any other
field: refresh `display_label` when the response carried it, keep it otherwise.
`display_label` is user-visible (it drives `__repr__`, `node.py:298`), so leaving it
stale after a refresh would visibly violate the guiding rule. `id` is exempt (it is
the merge key). `hfid` is derived from attributes, so it refreshes once attributes
merge.

### Kind change -> full replace, not merge

If the incoming node's concrete kind (`get_kind()`, == GraphQL `__typename`) differs
from the stored node's kind for the same uuid, the node was migrated to another kind
(the `ConvertObjectType` mutation, `convert_object_type.py`, converts in place and
preserves the uuid). Merging field-by-field across two schemas is incoherent - it
would leave phantom attributes/relationships from the old kind. In that case
**discard the stored entry and store the incoming node wholesale**, regardless of the
`merge` setting (grill 1b, 2026-07-02). This is the one case where the store object
identity is replaced even in merge mode - a deliberate exception to "mutate in place"
(D2). Purge the old kind's `_hfids` entries on replace so the index does not point at
the discarded object. Misfire risk is low: GraphQL `__typename` is always the concrete
kind, so a peer fetched via a generic relationship still reports its concrete kind.

### Object identity

Merge mutates the *existing* stored object and keeps its `_internal_id`. This
removes the duplicate `_objs` entries and keeps `store.get(id)` returning a stable
object across repeated fetches. Equality is unaffected: `InfrahubNode.__eq__` /
`__hash__` are id-based (`node.py:717-723`), so `node == client.store.get(node.id)`
remains true.

### Decisions deliberately taken

1. **Local edits win over a re-fetch.** Honour `value_has_been_mutated`
   (`attribute.py:100`) and `_peer_has_been_mutated` so re-collecting the same
   info never clobbers unsaved in-memory changes. Least surprising.
2. **Merge is the default.** Re-collecting the same information is therefore
   idempotent and only ever refreshes or adds knowledge.
3. **`fetched-None` counts as fetched.** The presence flag means "present in the
   response," not "value is non-null," so a genuine server-side clear still
   overwrites a stale cached value.

### Known limitation -> escape hatch

Merge can never *forget* a field that was cached earlier but not re-fetched (for
example, to observe that a relationship no longer exists when your refresh query
did not select it). This is the one case where a full replace is wanted. Provide
an explicit opt-out rather than guessing. It lives in three layers, mirroring how
`populate_store` / `pagination_size` already work (config default -> per-call
override):

1. **Implementation:** `NodeStoreBranch.set()` / `NodeStoreBase._set()` in
   `store.py` - the only place that writes `_objs`.
2. **Per-call control:** a `merge` argument on `NodeStore.set()` /
   `NodeStoreSync.set()` (`store.py:344`/`432`) and on the query methods `get` /
   `all` / `filters` (and sync variants), placed next to the existing
   `populate_store` argument. It threads into the `store.set(...)` calls at
   `client.py:1164`/`1168`/`2903`/`2907`.
3. **Global default / opt-out:** a field on `Config` (`config.py`), passed into the
   store at construction (`client.py:358`, currently
   `NodeStore(default_branch=self.default_branch)`). Defaults to merge.
   `InfrahubClient(config=Config(<option>=...))` restores the pre-1.23.0
   replace-everything behaviour in one place, and (like other `Config` bools) can
   be set via environment variable without code changes.

Resolution chain: **config default -> store default -> per-call `merge=` override.**

`merge=False` (or the config opt-out) clears prior knowledge of the node and stores
exactly what was fetched. The `at`/timestamp case (store is partitioned by branch,
not by `at`) is the practical reason this hatch earns its place.

#### Naming the config option (needs a decision)

`store_merge: bool` is terse and does not, on its own, say what it does. Two ways to
fix that, pick one:

- **Bool with a description that carries the meaning**, for example:

  ```python
  store_merge: bool = Field(
      default=True,
      description=(
          "When True, re-querying a node already in the store updates only the "
          "fields that were fetched and preserves previously fetched attributes "
          "and relationships. When False, the latest query fully replaces the "
          "stored node, which can drop data fetched by earlier queries "
          "(the pre-1.23.0 behaviour)."
      ),
  )
  ```

- **An enum** (consistent with existing `Config` enums such as `InfrahubClientMode`,
  `RecorderType`), e.g. `store_update_mode: StoreUpdateMode` with `MERGE` / `REPLACE`.
  More self-documenting at the call site, more code.

Whichever is chosen, the description must spell out the behaviour *and* name the
default, so the option is understandable without reading this plan.

## 4. Save-path safety (verified)

Adding a presence flag to `Attribute` does **not** change what gets written on
save. `Attribute._initialize_graphql_payload` (`attribute.py:148-151`) only emits
`{"value": None}` when the attribute was deliberately cleared
(`optional and value_has_been_mutated`); otherwise it emits an empty payload that
`node.py:458` drops from the mutation. Serialization keys on *mutation*, never on
null-ness or presence. The new flag is consumed solely by the store merge logic.

## 5. Implementation stages

Single PR, layered commits so the mechanism is reviewable end to end (see section
8 for the alternative split).

### Stage 1 - Presence flags (no behaviour change)

Add the "present in this response" signal everywhere the merge needs it:

- `RelatedNode` - add a presence flag (separate from `initialized`, which stays as
  the "has a peer" predicate other code relies on). Set it in `_init_relationships`
  (`node.py:898`/`928`) from `rel_schema.name in data`. Required for cardinality-one
  and hierarchical-`parent` merges to handle move-to-root / cleared relationships.
- `Attribute` - the attribute presence flag described below.

#### Stage 1a - Attribute presence flag

- `attribute.py` - add `initialized: bool = True` to `Attribute.__init__` and
  store it (`self.initialized`). Default `True` preserves behaviour for manual
  construction and every existing call site.
- `node.py:269` `_init_attributes` - compute presence unambiguously and pass it:

  ```python
  present = isinstance(data, dict) and attr_schema.name in data
  Attribute(..., data=attr_data, initialized=present)
  ```

  Detection must live here, not solely in `Attribute.__init__`, because the
  manual-construction path passes a bare scalar that `__init__` cannot tell apart
  from "absent."
- Verify nothing reads attribute state in a way the new field disturbs (save path
  already verified in section 4).

### Stage 2 - Store merges relationships instead of overwriting

- `store.py` `NodeStoreBranch.set()` - if `node.id` already maps to a stored
  object, merge into that object and keep its `_internal_id` instead of inserting
  a duplicate. Update `_keys` / `_uuids` / `_hfids` to the retained internal id.
- Implement the relationship half of the merge rule, gated on
  `RelationshipManager.initialized` / `RelatedNode.initialized`, with member-list
  replacement for cardinality-many. Cover **all three** buckets:
  `_relationship_cardinality_one_data`, `_relationship_cardinality_many_data`,
  and `_hierarchical_data` (see C1).
- Resolve the return-value vs store-identity decision (C2) before writing this -
  it changes whether the query path swaps returned references.
- This stage (with the cardinality-one + hierarchical buckets) fixes the literal
  ticket reproduction.

### Stage 3 - Extend merge to attributes

- Consume `Attribute.initialized` in the merge: take the incoming attribute when
  present and not locally mutated; otherwise keep the stored one.
- Swap the whole `Attribute` object on take so metadata refreshes with the value.

### Stage 4 - Explicit replace escape hatch

- Add the per-call `merge` argument to `NodeStore.set` / `NodeStoreSync.set` and
  thread a matching argument through the query methods (`get`, `all`, `filters`,
  and the sync variants) next to `populate_store`.
- Add the global default to `Config` (see section 3 for the naming decision and the
  required description) and pass it into the store at construction (`client.py:358`).
- `merge=False` (or the config opt-out) removes prior knowledge of the node before
  storing the fresh copy.
- This is a public API change on three surfaces (query-method args, `store.set`,
  `Config`) -> needs sign-off per `AGENTS.md` before implementing.

### Stage 5 - Tests (section 7)

### Stage 6 - End-user documentation (section 6)

## 6. End-user documentation (must ship with the change)

The store behaviour is user-visible and the change alters a long-standing
(buggy) behaviour, so the docs are part of the deliverable, not a follow-up.

**Guiding requirement - every behaviour change must be made clear.** This is a
hard gate on the work, not a documentation nicety:

- Any change to observable behaviour (the default merge, shared/living objects,
  returned-vs-stored object differences) must be stated explicitly in the guide
  *and* called out in the changelog / release notes, with before/after wording so a
  user upgrading to 1.23.0 can tell what changed and why.
- Any new configuration option must ship with a self-explanatory `description`
  (see section 3) that states what it does and its default. A reader who has never
  seen this plan must be able to understand the option from the description alone.
  A terse name (`store_merge`) is acceptable only if the description carries the
  meaning; otherwise prefer a clearer name or an enum.
- Frame the change as a bug fix, and document the opt-out, so the minor-version
  classification holds (see the version note at the top).

Update `docs/docs/python-sdk/guides/store.mdx` and/or add a topic under
`docs/docs/python-sdk/topics/` explaining:

1. **What the store guarantees now.** "The store keeps, per field, the freshest
   value the SDK has seen. Re-querying a node merges new data in; it does not
   replace the cached node wholesale." State plainly that this is a per-field
   freshness cache, not a point-in-time snapshot.
2. **Why a node can hold data from several queries.** Walk the ticket scenario:
   a deep fetch then a shallow re-fetch keeps the relationship, instead of losing
   it. This is the behaviour change users most need to understand.
3. **Re-collecting the same info is safe / idempotent.** It refreshes fetched
   fields and never drops un-fetched ones.
4. **Local unsaved edits win** over a re-fetch (so re-querying does not silently
   discard in-memory changes).
5. **How to force a clean replace** with `merge=False`, and when you would want
   it (observing server-side deletions of fields your refresh did not select;
   querying at a different `at`).
6. **Staleness caveat.** A cached value can still be out of date relative to the
   server, and the store does not track `at`.
7. **Returned object vs stored object (depends on C2).** If option (a) is chosen,
   document that the object returned by a query reflects only that query, while
   `store.get()` returns the merged view - they may differ.
8. **Shared, living objects (C3).** Document that the store hands back the same
   object across fetches and that re-querying a node refreshes the object other
   references already point at.

Follow `docs/AGENTS.md`: async/sync `Tabs`, language on every code block, callouts
for the behaviour-change note. Run `uv run invoke lint-docs` and, since this is a
hand-written guide (not generated), confirm `docs-validate` is unaffected.

A changelog / release-notes entry calling out the behaviour change explicitly is
**required** (see the guiding requirement above), not optional. Ride the Infrahub
1.11.0 release attention to surface it.

## 7. Testing

Unit tests in `tests/unit/` (see `tests/AGENTS.md`), async and sync:

- **Relationship regression (the ticket):** deep fetch of a node with a
  relationship, then a shallow fetch of the same node as a related node; assert
  the relationship survives in the store and `store.get(id)` is the enriched
  object.
- **Attribute regression (symmetric, currently unreported):** fetch a node with
  attributes A and B; re-fetch selecting only A; assert B survives in the store.
- **Refresh updates fetched fields:** changed attribute / changed relationship
  peers on re-fetch are reflected, including a cardinality-many peer removal.
- **Move reflected (cardinality-one / hierarchical):** node's `parent` changes
  from A to B on re-fetch with prefetch -> store shows B.
- **Move-to-root reflected (the `RelatedNode.initialized` trap):** node's `parent`
  is cleared on re-fetch with prefetch -> store shows no parent. This is the test
  that fails if the merge gates on `RelatedNode.initialized` instead of the new
  presence flag.
- **Not re-fetched -> kept:** re-fetch without prefetch leaves the cached `parent`
  untouched.
- **`fetched-None` overwrites:** an attribute that genuinely becomes null on the
  server overwrites a previously non-null cached value.
- **Local edits win:** mutate in memory, re-fetch the same info, assert the local
  value is preserved.
- **No duplicates:** after repeated fetches of one UUID, `_objs` / `_uuids` /
  `_hfids` hold exactly one entry for it; object identity is stable.
- **`merge=False`:** prior knowledge is dropped and only fetched fields remain.
- **Save unaffected:** a merged node serializes the same set of fields on save as
  before (guards the section 4 invariant).
- **Hierarchical relationships (C1):** deep then shallow fetch of a hierarchical
  node keeps parent / children / ancestors / descendants in the store.
- **Custom key consistency (incidental fix):** after a re-fetch,
  `store.get(custom_key)` and `store.get(uuid)` return the same object (today they
  diverge because `_keys` still points at the old internal id).
- **Return vs store identity (C2):** assert the documented behaviour of whichever
  option is chosen, so a future change does not regress it silently.
- **Aliased / fragment-inlined query (C6):** presence detection still fires when
  fields arrive under aliases.

Run `uv run invoke format lint-code` and `uv run pytest tests/unit/`.

## 8. Rollout / PR strategy

Recommended: **one PR, layered commits** (stages 1-6), so reviewers see how the
presence flag feeds the merge and the bug fix lands atomically. The presence flag
is inert on its own, which is why splitting along the flag/merge seam is a poor
idea.

Acceptable alternative if the ticket fix must ship sooner: split along the
relationship/attribute seam.

- PR 1: stage 2 (relationship merge) - fixes IHS-138 literally, uses existing
  `initialized`, lowest risk.
- PR 2: stages 1 + 3 + 4 (attribute presence flag, attribute merge, escape hatch)
  - the generalization plus the debatable policy calls.

Do not split along the flag/merge seam (flag PR then merge PR): the flag PR would
be unexplainable dead code.

## 10. Failure scenarios, lurking bugs, and gaps

These were found while reviewing the plan against the code. Items C1-C3 need a
decision before coding starts.

### C1 - Hierarchical relationships are easy to miss (would re-introduce the bug)

Covered in section 3 ("all three relationship buckets"). Called out here because a
merge written against `self._relationships` looks correct, passes the ticket's
relationship test, and still silently clobbers parent/children/ancestors/
descendants. Add an explicit hierarchical-relationship regression test.

### C2 - The query methods return a different object than the store keeps

`get` / `all` / `filters` build fresh nodes and `return nodes` (`client.py:1162`),
but merge keeps the *existing* store object. After the change,
`client.get(id) is client.store.get(id)` is no longer true, and the returned
object does not benefit from the merge (only the store copy does). `__eq__` /
`__hash__` are id-based (`node.py:717-723`), so value equality and the documented
`tag == tag_in_store` example survive; identity (`is`) does not.

Decision required - pick one:

- **(a) Accept divergence.** Store is the canonical, merged copy; returned objects
  are per-query snapshots. Simplest, lowest blast radius. Must be documented
  loudly so users do not expect the returned object to carry merged data.
- **(b) Return the canonical object.** After merging, the query path returns the
  retained store object instead of the freshly built one. Gives "one object per
  UUID" coherence but is more invasive (the return path must map incoming ->
  canonical) and changes what a caller gets back from a query.

Whichever is chosen, audit internal callers that assume the returned object is the
stored object: `RelatedNode.fetch()` (`related_node.py:367`/`463`) caches the
`client.get` result as `_peer`, and `save()` (`node.py:1287`/`2471`) calls
`store.set(node=self)`.

### C3 - Merge mutates objects the user already holds

Today each query builds independent objects, so a reference the user is holding is
stable. Merge-into-existing means an unrelated query that re-fetches the same UUID
will mutate the object the user's variable points at (refreshing fetched
attributes, replacing fetched relationships). This is inherent to "one living
object per UUID" and may be the right model, but it is a new, surprising behaviour
and must be a documented, deliberate decision. "Local edits win" softens it for
mutated fields, but un-mutated fields still change under the caller.

### C4 - Direct `_peer` references shadow the merged store copy

`RelatedNode.peer` returns a cached `self._peer` if set, falling back to
store-by-id only otherwise (`related_node.py:404-411`). `.fetch()` and explicit
assignment set `_peer` directly, so a relationship resolved that way will ignore
later store merges. The normal prefetch path resolves peers by id through the
store (which is why the store-level merge fixes the ticket), so this affects only
explicitly fetched/assigned peers. Document the limitation; do not try to
invalidate `_peer` caches as part of this change.

### C5 - `store.set()` default (RESOLVED: merge by default, uniformly)

Originally proposed as replace-by-default for the explicit `set()`. **Decided
otherwise (see `decisions.md` D3):** the store merges uniformly, with no
entry-point special-casing - `store.set()` merges just like the query path. Replace
is opt-in only, via `store.set(node, merge=False)` or `store_merge=False`. The
`store.set()` docstring must state that it merges by default and how to force
replace. Update the `store.mdx:147` example accordingly so "store this object"
does not read as "replace."

### C6 - Aliased fields / fragment inlining vs the presence check

`from_graphql` runs `_strip_alias` (`node.py:894`) before init, and a
fragment-inlining feature exists (`dev/specs/infp-496-graphql-fragment-inlining`).
If a queried field arrives under an alias that strip-alias does not normalise to
the schema name, `attr_schema.name in data` reads false and the merge skips a
field that *was* fetched (silent staleness). Add a test that exercises aliased /
fragment-inlined queries and assert presence detection still fires.

### C8 - `RelatedNode.initialized` means "has a peer," not "was fetched"

`RelationshipManager.initialized` is `data is not None` (a true fetched signal),
but `RelatedNode.initialized` is `bool(self.id) or bool(self.hfid)`
(`related_node.py:189`) - "has a peer." A fetched-but-empty cardinality-one
relationship (move to root, optional relationship cleared) reports
`initialized == False`, indistinguishable from "not fetched." Gating the merge on
it would keep a stale `parent` after a move-to-root - the opposite of expected.
Fix: add a presence flag to `RelatedNode` (Stage 1) and gate the merge on it. This
is the single most likely "looks correct, ships a bug" mistake in this work.

### C7 - Minor

- Attribute metadata staleness on wholesale `Attribute` swap (see section 3 caveat).
- Compute and register `_uuids` / `_hfids` / `_keys` from the merged object
  *after* merging; the hfid may change when an hfid-component attribute is
  refreshed.
- Threaded sync usage widens the read-modify-write window in `set()` (asyncio is
  unaffected). Pre-existing; note, do not fix here.

## 11. Open questions

Decided (see `decisions.md`, all settled 2026-07-01):

- **Version / classification:** SDK 1.23.0, semver minor, shipped as a bug fix with
  a required opt-out and a required behaviour-change note (see top + section 6).
- **Where the merge option lives:** `Config` default -> store default -> per-call
  `merge=` override (see section 3).
- **D1 - returned vs stored object:** query methods return the per-query object;
  the store holds the merged canonical copy.
- **D2 - living objects:** accepted; one always-current merged object per node,
  local edits protected.
- **D3 / C5 - `store.set()` default:** merge by default, uniformly; replace is
  opt-in via `merge=False` / `store_merge=False`.
- **D4 - config option:** bool `store_merge` with a full description.
- **D5 - presence-flag name:** `is_fetched`, uniform accessor on all three field
  types.
- **D6 - `merge=False` scope:** node entry only; peers handled independently.

Decided during implementation (see section 13 and `decisions.md`):

- **Public API sign-off:** granted with the go-ahead to implement the full plan.
  Shipped surfaces: `merge: bool | None` on `get`/`all`/`filters` and `store.set`,
  and `Config.store_merge`. `populate_store` keeps its `bool = True` signature.
- **D7 - mutation-flag lifecycle:** reset on successful save; merge propagates
  pending markers.
- **D8 - same-peer identity fields:** presence-gated; full refresh on peer change.
- **D9 - timestamp-coherent store:** supersedes grill item 3's skip-by-default
  mechanism; the store holds one `at` context per branch and refuses (warn + skip)
  mismatching populations.

## 12. Grill review outcomes (2026-07-02)

Stress-tested the plan against overall impact and the other in-flight specs
(`infp-496-graphql-fragment-inlining` is Implemented; `infp-504-artifact-composition`
in flight). Findings, all accepted:

1. **Node-level scalars in merge scope.** `display_label` / `typename` are merged,
   gated on presence (section 3). Folded in.
2. **Kind change -> full replace.** `typename` differing for the same uuid means a
   `ConvertObjectType` migration; replace wholesale instead of merging (section 3).
   Folded in.
3. **`at` (time-travel) queries skip the store by default.** The store is not
   `at`-aware, so a historical read must not blend into the live cache. New rule:
   when `at` is set, default `populate_store=False`; if the caller explicitly passes
   `populate_store=True`, honour it but force `merge=False` (replace, never blend).
   This is itself a behaviour change from today (where `at` reads populate the store)
   and must be in the migration note. *Superseded during implementation by D9
   (section 13): the shipped mechanism is a timestamp-coherent store instead.*
4. **Attribute property/metadata fidelity.** Merge field-by-field into the existing
   `Attribute`, not a blind object-swap, so value-only re-fetches don't null cached
   `source`/`owner`/`is_protected` etc. (section 3). Folded in.
5. **Blast radius / release gate.** Internal SDK reliance is minimal and additive
   (only `related_node` peer resolution and `save()` touch the store, both benefit).
   Risk is external: `client.get(id) is client.store.get(id)` identity loss (D1) and
   `at` no longer populating (item 3). Make the **Ansible collection** and
   **`infrahubctl`** integration suites a pre-release gate for 1.23.0, and enumerate
   both changes with before/after in the migration note.

Lower-priority (noted, not blockers):

- **Unbounded store growth.** Merge reduces growth (dedups today's duplicates) and
  the store is per-client, so generator/transform runs stay bounded. Out of scope;
  possible future `store.clear()` / eviction.
- **Fragment inlining / custom aliases (downgrades C6).** Store population uses
  SDK-generated queries (canonical field names + `__alias__`, normalised by
  `_strip_alias`); fragment inlining acts on hand-authored `.gql` via
  `execute_graphql`, which does not feed store population the same way. Downgrade C6
  to a verification test, not a risk.
- **Thread-safety.** Merge adds a read-modify-write in `set()`; fine under asyncio,
  and sharing one sync client across threads was already unsafe. Document "the store
  is not thread-safe"; do not fix here.

### Additional tests from the grill

- `display_label` refreshes on re-fetch that includes it; is kept when absent.
- Kind conversion: convert a node to another kind, re-fetch -> store holds the
  new-kind object, old-kind-only attributes are gone, `_hfids` has no stale entry.
- Value-only re-fetch preserves previously fetched attribute `source`/`owner`.
- `at` query does not populate the store by default; `populate_store=True` + `at`
  replaces (does not blend).
- SDK prefetch/hierarchical queries still map to schema names after `_strip_alias`
  (guards the fragment/alias concern).

## 13. Implementation outcomes (2026-07-02 .. 2026-07-04)

The feature was implemented as planned (stages 1-6, single PR, all D1-D6 decisions
honoured), then hardened after a full code review. What shipped differs from the
plan above in the following ways; the new decisions are recorded as D7/D8 in
`decisions.md`.

### Corrections found by the review

1. **Mutation-flag lifecycle (D7, new decision).** The plan gated "local edits win"
   on `value_has_been_mutated` / `_peer_has_been_mutated` / `_has_update`, assuming
   those flags meant "unsaved edit". They were in fact sticky - nothing ever reset
   them after a successful save - so any saved edit would have blocked merge
   refreshes of that field forever (permanent store staleness; the pre-merge replace
   semantics had masked this). Shipped fix, two halves: a successful
   `create()`/`update()`/`save()` now calls `_reset_mutation_tracking()`
   (`_process_mutation_result`, async and sync), and the merge *propagates* the
   markers from an unsaved incoming copy instead of clearing them, so a merged
   unsaved edit is still sent by the store copy's next save. This is a user-visible
   behaviour change (listed in the changelog): mutation tracking resets on save.
2. **Same-peer identity gating (D8, refines section 3).** "Peer identity always
   refreshes" was too coarse: a payload carrying only `node { id }` for the same
   peer would have nulled previously fetched `hfid`/`display_label`/`typename` and
   dropped the cached `_peer` (unreachable via SDK-generated queries, which always
   select all four, but reachable via `from_graphql` on custom payloads +
   `store.set`). Shipped rule: a *changed* peer takes the full incoming identity
   (moves and clears still work); the *same* peer only refreshes identity fields the
   incoming payload actually carried.
3. **`_data` baseline merges key-wise.** Section 3's field-by-field fidelity rule is
   also applied to the raw `_data` dict (the baseline `update()` diffs against), so
   a value-only re-fetch does not shrink `_data[name]` and cause `update()` to
   re-send untouched properties.

### Performance constraints added (not covered by the plan)

- `NodeStoreBranch.set()` is the hottest path in the SDK; the first implementation
  made store population O(N^2) via a linear hfid-index scan per set (measured: 30k
  inserts = 4.9s). The store now keeps reverse indexes (`_hfids_by_internal_id`,
  `_keys_by_internal_id`) so set/evict are O(1) per call (30k inserts = 0.03s).
- The per-field presence sets (`_fetched_fields` / `_fetched_properties`) are
  interned via `utils.intern_frozenset` - objects built from the same query shape
  share one instance. Without this the bookkeeping measured ~64% of an Attribute's
  memory footprint (~0.5 GB per 50k-node sync).

### Timestamp-coherent store (D9, supersedes grill item 3's mechanism)

Grill item 3 was first implemented as "skip the store when `at` is set unless the
caller explicitly opts in (then replace)", which required widening `populate_store`
to `bool | None` to detect an explicit `True`, and left `at` +
`prefetch_relationships` without working `.peer` resolution. Review discussion
replaced that mechanism: the store now holds **one timestamp context per branch**
(live, or one `at` instant), stamped by the first population. Same-context queries
use the store normally - a fully historical script gets complete store
functionality including merge and peer resolution, which the first mechanism could
not offer (its opt-in forced replace, quietly reviving the IHS-138 bug for
historical work). A mismatching population (live vs historical, or two different
instants) warns and skips the store, so nothing ever blends across timestamps -
strictly safer than both pre-1.23 (silent overwrite) and the first mechanism.
`populate_store` stays `bool = True` with no signature change. Known footgun,
documented: a per-call recomputed relative timestamp trips the mismatch warning;
compute `at` once and reuse it, or use one `client.clone()` per timestamp.

### Minor deviations from the plan text

- The presence flag on `RelatedNode` is a constructor parameter (like `Attribute`),
  not a post-construction assignment; presence detection lives in one helper
  (`InfrahubNodeBase._field_was_fetched`).
- Each field type owns its merge: `Attribute._merge`, `RelatedNodeBase._merge`,
  and `RelationshipManagerBase._merge` (the plan only implied the first two).
- Follow-up filed separately: generated typed protocols for test schemas
  (GitHub #1132), prompted by the test suite written for this feature.

Still pending from section 12: the 1.23.0 pre-release gate (Ansible collection +
`infrahubctl` integration suites).
