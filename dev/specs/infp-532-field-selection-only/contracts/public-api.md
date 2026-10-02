# Contract: Public API Changes

Library contract for [spec.md](../spec.md). Each change applies identically to the async and sync variants (FR-031). Signatures show only the new or changed parameters; `...` stands for the existing ones, which are unchanged in name, order and default.

## Query methods

```python
# InfrahubClient (async) and InfrahubClientSync, every @overload included
get(kind, ..., priority=None, only: list[str] | None = None, **kwargs)
all(kind, ..., priority=None, only: list[str] | None = None)
filters(kind, ..., priority=None, only: list[str] | None = None, **kwargs)
```

- `only` is the last explicit parameter, so existing positional calls keep working.
- `only=None`: today's behaviour, envelope included (FR-002, FR-017).
- `only=[...]`: exactly the named attributes and relationships, plus the identity floor `id`, `display_label`, `__typename`. Naming `hfid` adds the queried node's HFID (FR-001, FR-006, FR-007, FR-008).
- Raises `SelectionConflictError` if `include is not None` or `exclude is not None`, before any schema lookup or query (FR-005).
- Raises `SelectionFieldNotFoundError` for an unknown name, or a name that needs `fragment=True`, before the data query (FR-009, FR-011).
- Nodes returned from an `only` call, and the peer nodes built for them, raise `FieldNotLoadedError` on unknown reads in 1.x (FR-023).
- Under `only`, peer nodes are built and stored only when `prefetch_relationships=True`.
- `RelatedNode.peer` / `get()` on a reference whose peer was never fetched still raises `NodeNotFoundError`, and its message now says to call `fetch()` on the relationship or to query with `prefetch_relationships=True` (FR-026).

## Query generation helpers (public methods on node classes)

```python
InfrahubNode.generate_query_data_init(..., include_metadata=False, only: list[str] | None = None)
InfrahubNode.generate_query_data(..., include_metadata=False, only: list[str] | None = None)
InfrahubNode.generate_query_data_node(..., include_metadata=False, only: list[str] | None = None)
# InfrahubNodeSync: identical
```

These generate the same structures the query methods send. `generate_query_data_init` raises `SelectionConflictError` under the same rule.

## Peer hydration

```python
RelatedNode.fetch(timeout=None, priority=None, only: list[str] | None = None, exclude: list[str] | None = None)
RelationshipManager.fetch(only: list[str] | None = None, exclude: list[str] | None = None)
# RelatedNodeSync / RelationshipManagerSync: identical
```

- `only` and `exclude` are mutually exclusive (`SelectionConflictError`) (FR-015).
- `only` is validated once against the relationship's declared peer kind (valid on the kind, or on any kind implementing it), before any request (FR-016).
- Each concrete peer kind is asked for the named fields it defines, plus the floor.
- Names are flat. Path syntax is not supported.
- With neither argument: today's behaviour (the default selection).

## Known-state check

```python
Attribute.is_loaded -> bool
RelatedNodeBase.is_loaded -> bool          # RelatedNode, RelatedNodeSync
RelationshipManagerBase.is_loaded -> bool  # RelationshipManager, RelationshipManagerSync
```

- `True` iff the SDK knows the value: present in the data the node was built from, assigned since, or the owning node has no `id` (FR-018, FR-019).
- Reading `is_loaded` never warns or raises.
- `RelatedNodeBase.initialized` and `RelationshipManagerBase.initialized` keep their current meanings.

## Detected reads

Reading any of these when `is_loaded` is false warns in 1.x and raises in strict mode:

| Object | Accessors |
|---|---|
| `Attribute` | `value` |
| `RelatedNode`, `RelatedNodeSync` | `id`, `hfid`, `hfid_str`, `display_label`, `typename`, `kind`, `initialized`, `peer`, `get()` |
| `RelationshipManager`, `RelationshipManagerSync` | `peers`, `peer_ids`, `peer_hfids`, `peer_hfids_str`, `is_from_profile`, `[index]` (and so iteration) |

Writing is never detected. Assigning `node.<attr>.value = …` or `node.<rel> = …` succeeds and makes the field known (FR-020). Cardinality-many writes (`add`, `extend`, `remove`) keep their existing contract: they raise `UninitializedError` until the manager is initialized.

`RelationshipManager.peers` becomes a property backed by private storage. Its setter is kept, so existing code that assigns or mutates the list in place keeps working.

## Errors and warnings (`infrahub_sdk.exceptions`)

```python
class FieldNotLoadedError(Error):
    kind: str
    field: str
    selection: str | None   # Selection label; None when the origin is unknown

class SelectionFieldNotFoundError(Error):
    kind: str
    field: str
    implementing_kinds: list[str]   # non-empty for the "needs fragment=True" case

class SelectionConflictError(Error):
    parameters: list[str]   # e.g. ["only", "include"]

class FieldNotLoadedWarning(FutureWarning): ...
```

## Message format

The text is the same for the warning and the error, except that the 1.x warning adds a final sentence. It contains no node id, so Python can de-duplicate warnings per call site.

| Case | Message |
|---|---|
| SDK selection | `<Kind>.<field> was not fetched (selection: <label>). Add it to the selection, or call fetch(), before reading it.` |
| Peer carrying only the identity floor | `<Kind>.<field> was not fetched: this node only carries the identity floor (peer of <Parent>.<rel>). Hydrate it with fetch(only=[...]) before reading it.` |
| Unknown origin | `<Kind>.<field> is not known to the SDK (origin unknown). Fetch the node with a selection that includes it before reading it.` |
| 1.x warning suffix | `This will raise FieldNotLoadedError in infrahub-sdk 2.0.`, appended after a space |

The warning's `stacklevel` points at the first frame outside the `infrahub_sdk` package.

## Unchanged

- `include` and `exclude` semantics, and the existing `ValueError` when a name appears in both (FR-003, FR-004, FR-028).
- Peer envelopes still request `hfid`, and so does the default (no `only`) query envelope.
- Client store semantics.
- CLI commands and options. Rendering skips unknown fields (FR-030), and options don't change.
