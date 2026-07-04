# IHS-138 - Decision sign-off sheet

One row per open decision from [`plan.md`](./plan.md) section 11. Each has a
recommendation and the reasoning; mark **Accept** / **Override** and note any
change. Nothing in Stage 1 (presence flags) depends on these - they gate Stage 2
onward.

Already settled (recorded in the plan, listed here for completeness):

- **Version:** SDK 1.23.0, semver minor, shipped as a bug fix with a required
  opt-out and a required behaviour-change note.
- **Where the option lives:** `Config` default -> store default -> per-call
  `merge=` override.

---

## D1 - Returned object vs stored object (C2)

**Question.** After a re-fetch, the store keeps the merged canonical object. What
does a query method (`get` / `all` / `filters`) return?

- **(a) Return the freshly built per-query object** (diverges from the store copy).
- **(b) Return the canonical merged store object.**

**Recommendation: (a).**

**Why.**

- Minor-version safe: what `client.get()` returns is byte-for-byte what it returns
  today (exactly the fields this query asked for). Only `store.get()` gets richer.
  Option (b) changes every query's return value to carry data the caller did not
  request - much harder to call non-breaking.
- It shrinks the D2 blast radius: the only "living" object is the internal store
  copy; returned objects are stable per-query snapshots.
- Less code: (b) needs the query path to map incoming -> canonical and swap
  returned references.
- Clean mental model: "the return value is this query's result; the store
  accumulates across queries."

**Cost / what to verify.** `client.get(id) is client.store.get(id)` stops being
true (it holds today). Value equality `==` still holds (id-based, `node.py:720`).
Add a `save()` test: `save()` calls `store.set(self)`, so `self` merges into the
canonical copy while the caller keeps `self` - confirm no field is revived that
the save did not touch.

**Decision: ACCEPTED (a).** Query methods return the per-query object; the store
holds the merged canonical copy. Guiding rule agreed with the reporter: *"queries
hand you what you asked for; the store remembers the union of everything it has
seen."*

---

## D2 - In-place mutation / living objects (C3)

**Question.** Merge mutates the existing stored object, so a `store.get()`
reference can change under the caller when an unrelated query re-fetches that node.
Is that the intended model?

**Recommendation: accept it, documented, with local-edit protection.**

**Why.**

- It is the correct property for a cache: every store reference points at the one
  canonical object, which is always current. The alternative (merge into a new
  object, replace the entry) leaves previously handed-out `store.get()` references
  stale and diverging from the store - worse.
- Under D1(a) the surprise is confined to code that deliberately holds a
  `store.get()` result across queries; plain query return values never mutate.
- Protect unsaved local edits: merge must skip fields flagged
  `value_has_been_mutated` (`attribute.py:100`) / `_peer_has_been_mutated`
  (`related_node.py:74`), so re-querying never discards in-memory changes.

**Cost.** New, documented behaviour. Covered by the section 6 "behaviour change
must be clear" requirement.

**Decision: ACCEPTED.** The store keeps one always-current, merged object per node;
`store.get()` references reflect later fetches. Unsaved local edits are protected.

---

## D3 - Default for the public `store.set()` (C5)

**Question.** The query-population path defaults to merge (the fix). What should the
public `store.set(node=...)` default to?

- **(a) `merge=False` (replace) by default**, opt into merge.
- **(b) `merge=True` (merge) by default**, same as queries.

**Recommendation: (a) - public `set()` defaults to replace.**

**Why.**

- "set" reads as an imperative "make the store hold this," like `dict[k] = v`.
  Merge is the enrichment behaviour the *query* path needs, not what an explicit
  `set` implies.
- Preserves the documented contract ("store this object", `store.mdx:147`). That
  example sets a fresh object under a custom key, usually with no prior entry, so
  replace and merge are identical there - no example breaks.
- The IHS-138 bug lives in the query path, not in manual `set()`. Keep the default
  change where the bug is; leave the explicit call predictable.
- A user who wants enrichment passes `merge=True`.

**Note.** This means the default differs by entry point: queries follow
`Config.store_merge` (default merge); `set()` defaults to replace regardless. That
is intentional and should be stated in the `set()` docstring.

**Decision: OVERRIDE -> (b) merge by default, uniformly.** The recommendation above
was not taken. Agreed model: *anything that lands in the store gets merged*, with no
special-casing by entry point - `store.set()` merges just like the query path. This
is the simpler, single-rule mental model. Consequence: **replace is opt-in only** -
the sole way to store a node verbatim / drop previously cached data is
`store.set(node, merge=False)` or the `store_merge=False` config opt-out. The public
`store.set()` docstring must state that it merges by default and how to force
replace.

---

## D4 - Config option name and type

**Question.** How is the global default expressed on `Config`?

- **(a) Bool `store_merge` with a full `description`** (drafted in plan section 3).
- **(b) A clearer bool name** (e.g. `merge_store_results`).
- **(c) Enum `store_update_mode: StoreUpdateMode` (`MERGE` / `REPLACE`)**, matching
  existing `Config` enums (`InfrahubClientMode`, `RecorderType`).

**Recommendation: (a) - bool `store_merge` carried by its description.**

**Why.**

- Type-consistency with the per-call `merge: bool` argument. An enum on `Config`
  plus a bool per call is a mismatch; keeping both bool is simplest to reason about.
- The clarity the user asked for is delivered by the `description` (which states
  both behaviours and the default), per the section 6 hard requirement - so the
  terse name is acceptable.
- Enum is the fallback if call-site self-documentation is valued over type
  consistency, and we are willing to accept the enum/bool split (or make the
  per-call arg accept the enum too).

**Decision: ACCEPTED (a).** Bool `store_merge` with the full description. Revisit only
if the description proves insufficient in review.

---

## D5 - Internal presence-flag naming

**Question.** Name for the new "present in this response" flag on `Attribute` and
`RelatedNode`.

**Recommendation: `is_fetched`, with a uniform accessor across all three field
types.**

**Why.**

- `RelatedNode` already has `initialized` meaning "has a peer"
  (`related_node.py:189`) - a *different* concept - so the new flag there cannot be
  called `initialized` without a confusing collision.
- `RelationshipManager.initialized` already means "was fetched." Expose
  `is_fetched` on it as a thin alias of `initialized`, add a real `is_fetched`
  flag to `Attribute` and `RelatedNode`, and the merge code can branch uniformly
  on `field.is_fetched` regardless of field type.
- Internal only (not public API), so low stakes - but the uniform accessor removes
  per-type special-casing in the merge.

**Decision: ACCEPTED.** `is_fetched` on `Attribute` and `RelatedNode`; uniform
`is_fetched` accessor on `RelationshipManager` aliasing its existing `initialized`.

---

## D6 - Scope of `merge=False` (replace)

**Question.** When a node is stored with `merge=False`, does it also drop that
node's relationship peers from the store, or only replace the node's own entry?

**Recommendation: only replace the node's own entry.**

**Why.**

- Peers are independent store entries that other nodes may reference; cascading
  eviction could break unrelated references.
- Peers fetched in the same query go through their own `set()` calls and follow the
  same `merge` flag independently. No special cascade needed.

**Decision: ACCEPTED.** `merge=False` replaces the node's own entry only; peers are
handled independently.

---

## D7 - Mutation-flag lifecycle (added during implementation, 2026-07-04)

**Question.** D2 protects "unsaved local edits" via the mutation flags
(`value_has_been_mutated`, `_peer_has_been_mutated`, `_has_update`). The code review
showed those flags were sticky - never reset after a successful save - so a saved
edit would block merge refreshes of that field forever, and the store would serve
the stale saved value even after the server changed. What is the flag lifecycle?

**Decision: reset on save, propagate on merge.**

- A successful `create()`/`update()`/`save()` resets all three flag types
  (`_reset_mutation_tracking()` at the end of `_process_mutation_result`): the
  persisted values count as server state from then on.
- The merge propagates the markers from an unsaved incoming copy instead of
  clearing them, so an unsaved edit merged into the store (manual `store.set`)
  keeps its will-be-saved status and is still sent by the store copy's next save.

**Why.** The two halves depend on each other: propagation is only safe because
saving resets the flags (a freshly saved copy no longer reads as "pending"), and
resetting is what makes "local edits win" mean *unsaved* edits, which is what D2
intended. Consequence, listed in the changelog: mutation tracking now resets after
a successful mutation, so a second `update()` no longer re-sends relationship edits
that were already persisted.

---

## D8 - Same-peer identity fields gate on presence (refines the merge rule)

**Question.** The plan said cardinality-one peer identity "always refreshes" when
the relationship was fetched. A payload carrying only `node { id }` for the *same*
peer would then null previously fetched `hfid`/`display_label`/`typename`/`kind`
and drop the cached `_peer` - the silent-loss class this feature exists to prevent
(reachable via `from_graphql` on custom payloads + `store.set`, not via
SDK-generated queries).

**Decision: split by peer change.** A changed peer (different id, including cleared
to none) takes the full incoming identity, so moves and move-to-root behave as
specified. The same peer only refreshes the descriptive identity fields the
incoming payload actually carried - consistent with how attribute properties and
edge properties already merge.

---

## D9 - Timestamp-coherent store (supersedes grill item 3's mechanism, 2026-07-04)

**Question.** Grill item 3 decided historical (`at`) reads must not blend into the
live cache. The first implementation made `at` queries skip the store by default,
with an explicit `populate_store=True` opt-in that forced replace. That required
widening `populate_store` from `bool = True` to `bool | None = None` (to detect an
explicit `True`), left `at` + `prefetch_relationships` without `.peer` resolution,
and - because the opt-in forced replace - quietly revived the IHS-138 bug for
fully-historical scripts. Was the signature change actually needed?

**Decision: no - make the store timestamp-coherent instead.** The store holds one
timestamp context per branch: live data, or one `at` instant, stamped by the first
population. Same-context queries use the store normally, so a script running all
its queries at one `at` gets full store functionality (merge, `.peer`, hfid
lookups). A mismatching population (live vs historical, or two different instants)
emits a warning and skips the store for that query; the query itself still returns
its results.

**Why.**

- The incoherence grill item 3 feared comes only from *mixing* timestamps; a
  consistent-`at` session is exactly as coherent as a live one and deserves the
  same cache behaviour, including the merge semantics this whole feature adds.
- `populate_store: bool = True` is restored - no public signature change, no `None`
  sentinel in a boolean parameter.
- Strictly safer than both alternatives considered: pre-1.23 silently overwrote
  live entries with historical data; skip-by-default silently degraded historical
  scripts. Warn-and-skip makes the mismatch visible without breaking mixed scripts
  (which are safer than they were on 1.22, not worse).
- Mismatch policy is warn + skip rather than raise: raising would break scripts
  that mix `at` and live queries, which worked (subtly wrong) before, and this
  ships as a semver-minor bug fix.
- Documented footgun: recompute a relative timestamp per call and every query
  after the first trips the warning - compute `at` once, or use one
  `client.clone()` per timestamp (the context is per client store, per branch).

---

## Summary table

| ID | Decision | Outcome |
|----|----------|---------|
| D1 | Returned vs stored object | Return per-query object; store holds the merged canonical copy |
| D2 | In-place mutation model | Accept; one always-current merged object per node; protect local edits |
| D3 | `store.set()` default | **Merge by default, uniformly** (override); replace is opt-in via `merge=False` |
| D4 | Config option name/type | Bool `store_merge` + full description |
| D5 | Presence-flag name | `is_fetched`, uniform accessor on all three field types |
| D6 | `merge=False` scope | Node entry only; peers handled independently |
| D7 | Mutation-flag lifecycle | Reset on successful save; merge propagates pending markers (2026-07-04) |
| D8 | Same-peer identity fields | Presence-gated for the same peer; full refresh on peer change (2026-07-04) |
| D9 | `at` and the store | Timestamp-coherent per branch; mismatching populations warn + skip (2026-07-04) |

**Guiding rule:** queries hand you what you asked for; the store remembers the union
of everything it has seen. Replace happens only when explicitly requested
(`merge=False` / `store_merge=False`).

All decisions are settled and implemented (D1-D6 as planned; D7/D8/D9 added during
the 2026-07-04 code-review hardening - see plan section 13 for the full list of
implementation outcomes, including the performance constraints on `store.set()`).
The remaining external gate is the 1.23.0 pre-release run of the Ansible collection
and `infrahubctl` integration suites.

## Grill refinements (2026-07-02)

Stress-testing the plan (see plan section 12) added these, all accepted:

- **Merge scope** also covers node-level scalars (`display_label`, `typename`) and
  merges attributes/properties field-by-field (not object-swap).
- **Kind change is a documented exception to D2:** if `typename` differs for the same
  uuid (a `ConvertObjectType` migration), the store entry is *replaced* wholesale, not
  mutated in place - merging across schemas is incoherent.
- **`at` (time-travel) queries skip store population by default** (behaviour change
  from today; must be in the migration note). Explicit `populate_store=True` + `at`
  replaces rather than blends. *Superseded by D9:* the shipped mechanism is a
  timestamp-coherent store (one `at` context per branch, warn + skip on mismatch),
  which keeps the same goal - never blend timestamps - without the `populate_store`
  signature change.
- **Release gate:** Ansible collection + `infrahubctl` integration suites run against
  the 1.23.0 pre-release; migration note enumerates the D1 identity change and the
  `at` change with before/after.
