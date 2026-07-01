# IHS-138 - Merge nodes in the client store instead of overwriting

- **Ticket:** [IHS-138](https://opsmill.atlassian.net/browse/IHS-138) (GitHub [#413](https://github.com/opsmill/infrahub-sdk-python/issues/413))
- **Priority:** High
- **Affected versions:** observed on SDK 1.12.1
- **Target version:** SDK 1.23.0 (ships alongside Infrahub 1.11.0)
- **Status:** plan / not started

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
- For attributes, the cleanest implementation is to swap the whole `Attribute`
  object when it should be taken, so metadata (`is_default`, `is_from_profile`,
  `id`) refreshes with the value, not just `_value`. Caveat: if the re-fetch
  selected the value but not the property metadata, swapping wholesale can null
  those flags - preserve them from the stored attribute when the incoming ones are
  absent.

### "Field" means all three relationship buckets

A node holds relationships in **three** separate containers, and the merge must
iterate all of them or it reintroduces the bug on the ones it skips:

- `_relationship_cardinality_one_data` (`RelatedNode`)
- `_relationship_cardinality_many_data` (`RelationshipManager`)
- `_hierarchical_data` (parent / children / ancestors / descendants)

Note `self._relationships` (`node.py:117`) lists **only** `schema.relationships`,
so it does *not* include the hierarchical bucket. Do not drive the merge off
`self._relationships` alone.

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

### C5 - Manual `store.set()` should default to replace, not merge

`store.set(key=..., node=...)` is documented as "store this object"
(`store.mdx:147`). Defaulting it to merge would silently change that. Proposal:
the query-population path merges by default; the public `set()` defaults to
`merge=False` (explicit replace) and accepts `merge=True` opt-in. Revisit when
finalising the section 3 escape-hatch API.

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

Decided:

- **Version / classification:** SDK 1.23.0, semver minor, shipped as a bug fix with
  a required opt-out and a required behaviour-change note (see top + section 6).
- **Where the merge option lives:** `Config` default -> store default -> per-call
  `merge=` override (see section 3). Public API change -> needs `AGENTS.md` sign-off.

Still open:

- **C2 decision:** accept return-value vs store divergence (option a) or return
  the canonical object (option b)? Blocks stage 2. The minor-version framing favours
  (a) (it leaves query return values unchanged from today).
- **C3 decision:** confirm in-place mutation of held objects is the intended model
  (it follows from a shared store), and that it is documented as such.
- **C5 decision:** default `merge=False` for the public `store.set()` while the
  query-population path defaults to merge?
- **Config option naming:** terse bool `store_merge` (with the descriptive
  `description` in section 3) vs a clearer name vs a `StoreUpdateMode` enum.
- Naming of the attribute / `RelatedNode` presence flags: `initialized` (symmetry
  with `RelationshipManager`) vs `is_fetched` (clearer intent).
- Whether `merge=False` should also drop the node's relationship peers from the
  store, or only reset the node itself.
