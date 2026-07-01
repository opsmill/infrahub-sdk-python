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

**Decision:** ____________________

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

**Decision:** ____________________

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

**Decision:** ____________________

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

**Decision:** ____________________

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

**Decision:** ____________________

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

**Decision:** ____________________

---

## Summary table

| ID | Decision | Recommendation |
|----|----------|----------------|
| D1 | Returned vs stored object | (a) return per-query object; store is canonical |
| D2 | In-place mutation model | Accept, documented, protect local edits |
| D3 | `store.set()` default | (a) replace by default; queries merge by default |
| D4 | Config option name/type | (a) bool `store_merge` + full description |
| D5 | Presence-flag name | `is_fetched`, uniform accessor on all three types |
| D6 | `merge=False` scope | Node entry only; peers handled independently |

Once D1-D3 are settled, Stage 2 onward is unblocked. D4-D6 can be confirmed during
implementation without reblocking.
