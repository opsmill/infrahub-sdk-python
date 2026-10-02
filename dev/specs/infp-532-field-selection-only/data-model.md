# Data Model: Field Selection with `only` and Known-State Field Access

Phase 1 output for [plan.md](plan.md). This feature persists nothing. The "entities" below are in-memory concepts carried by nodes and field objects.

## Selection

The resolved selection of an SDK-generated query, bound to each node that query produced.

| Field | Type | Meaning |
|---|---|---|
| `only` | `tuple[str, ...] \| None` | Names passed to `only`, or `None` when `only` wasn't used |
| `include` | `tuple[str, ...] \| None` | Names passed to `include` |
| `exclude` | `tuple[str, ...] \| None` | Names passed to `exclude` |
| `strict` | `bool` | `True` iff `only` produced this node, directly or as a peer. Unknown reads on the node raise in 1.x (FR-023) |
| `peer_of` | `str \| None` | `"<Kind>.<relationship>"` when the node was built as a peer of a queried node |

### Rules

- At most one of `only` or (`include`, `exclude`) is set (FR-005). `include` and `exclude` may both be set.
- `describe()` gives the message label: `only=[...]`, `include=[...]`, `exclude=[...]`, `include=[...], exclude=[...]`, or `default selection`. For peers it's `peer of <Kind>.<rel>, fetched with <parent label>`.
- A peer's selection copies `strict` from its parent's.
- Immutable once bound.

### Lifecycle

Created by `client.filters` (which `get`, `all`, batch tasks and hydration all call). Bound to every node built from the response, and to peer nodes built by `_process_relationships`. Nodes built any other way have no selection.

## Identity floor

Fields always requested, whatever the selection.

| Context | Fields |
|---|---|
| Queried node (envelope) | `id`, `display_label`, `__typename` |
| Peer (cardinality-one or many, hierarchical) | `id`, `hfid`, `display_label`, `__typename` |

Floor names accepted in `only` as no-ops: `id`, `hfid`, `display_label`.

## Known state (per field)

Every attribute, cardinality-one relationship and cardinality-many relationship of a node has a known state.

| Field object | Private presence source | Owner |
|---|---|---|
| `Attribute` | Present flag: `name in data` at construction; set to `True` by the `value` setter | Owning node, bound by the node |
| `RelatedNode` (cardinality-one, `parent`) | Present flag: `name in data` at construction; a new `RelatedNode` created on assignment is present | Owning node, bound by the node |
| `RelationshipManager` (cardinality-many, `children`, `ancestors`, `descendants`) | Existing `initialized` (`data is not None`; `True` after `fetch()`) | Existing `node` reference |

### Derived check

`is_loaded = present or owner is None or not owner.id` (FR-018, FR-019).

### State transitions (one field)

```text
            built from data with the key ──▶ KNOWN (present)
            built from data without the key
              ├─ owner has no id ──────────▶ KNOWN (empty value, rule 3)
              └─ owner has an id ──────────▶ UNKNOWN

UNKNOWN ── caller assigns a value ────────▶ KNOWN (present)
UNKNOWN ── manager.fetch() ───────────────▶ KNOWN (cardinality-many only)
KNOWN (rule 3 only) ── node saved, gets id ▶ UNKNOWN
KNOWN (present) ── any ───────────────────▶ KNOWN
```

### Reading a field

This applies to the detected accessors listed in [contracts/public-api.md](contracts/public-api.md).

```text
is_loaded? ── yes ──▶ return value, no warning
     │
     no
     ▼
internal access active? ── yes ──▶ return today's value (None / []), silently
     │
     no
     ▼
strict (switch on, or owner.selection.strict)? ── yes ──▶ raise FieldNotLoadedError
     │
     no
     ▼
warn FieldNotLoadedWarning, return today's value (None / [])
```

## Read policy

| Element | Where | Value in 1.x | Value in 2.0 |
|---|---|---|---|
| Switch point `_STRICT_FIELD_ACCESS` | `infrahub_sdk/node/field_access.py` (private) | `False` | `True` |
| Internal-access flag | `contextvars.ContextVar[bool]` in the same module, entered by a context manager and decorator | Set during SDK-internal operations | Same |

## Errors and warnings

| Type | Base | Raised or emitted when | Attributes |
|---|---|---|---|
| `FieldNotLoadedError` | `Error` | Detected read while strict | `kind: str`, `field: str`, `selection: str \| None` |
| `FieldNotLoadedWarning` | `FutureWarning` | Detected read while not strict | n/a (message only) |
| `SelectionFieldNotFoundError` | `Error` | A name in `only` resolves nowhere (FR-009), or needs fragments (FR-011) | `kind: str`, `field: str`, `implementing_kinds: list[str]` |
| `SelectionConflictError` | `Error` | `only` with `include` or `exclude` (FR-005) | `parameters: list[str]` |

None derives from `AttributeError`, `UninitializedError` or `ValueError` (FR-028).

## Validation rules for `only`

| Input | Outcome |
|---|---|
| `only=None` | Default selection path (FR-002) |
| `only=[]` | Identity floor only (FR-007) |
| Name is a floor name | Accepted, no-op (FR-008) |
| Name is an attribute, relationship or (hierarchical kinds) hierarchical field of the kind | Selected |
| Generic kind, name on an implementing kind only, `fragment=True` | Selected in that kind's fragment (FR-010) |
| Generic kind, name on an implementing kind only, `fragment=False` | `SelectionFieldNotFoundError` naming fragments (FR-011) |
| Name nowhere | `SelectionFieldNotFoundError` naming the field (FR-009) |
| `only` with `include is not None` or `exclude is not None` | `SelectionConflictError` before any schema lookup or query (FR-005) |
| Hydration: name valid on the declared peer kind (or any implementing kind) | Sent to each concrete peer kind that defines it (FR-016) |
