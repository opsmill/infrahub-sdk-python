# Data Model: Fetch Only the Named Fields with `only`

**Feature**: INFP-532 | **Date**: 2026-10-14 | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

This feature adds no stored data. It adds one parameter, one property on field objects and three error types. It also adds private state on nodes and field objects that records what the server returned.

## `only` parameter (public)

- **Type**: `list[str] | None`, default `None`.
- **Accepted by**:
  - `get`, `all` and `filters` on `InfrahubClient` and `InfrahubClientSync`;
  - `fetch` on `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync`.
- **Not accepted by** the public `generate_query_data*` methods, which do not change. Private methods build the query for `only`.
- **Values**:
  - `None`: the default set, exactly as today.
  - `[]`: `id`, `display_label` and `__typename` only.
  - A list of names. Each name is one of:
    - an attribute or relationship of the kind;
    - for a generic kind, an attribute or relationship of the generic or of any kind in `used_by`;
    - `parent`, `children`, `ancestors` or `descendants`, when the kind has a hierarchy;
    - `id`, `display_label` (accepted, add nothing) or `hfid` (requests the HFID the server stores, research R5).
- **Validation**:
  - `only` with `include` or `exclude` that is not `None` raises `FieldSelectionConflictError` before any request.
  - A name outside the list above raises `FieldNotFoundError` before the data query.
  - For `RelationshipManager.fetch`, every name must be accepted by every peer kind being fetched.
- **Duplicates**: allowed and ignored.

## "The response contained this field" record (private)

Kept on each field object of every node (research R6):

| Field object | Set to true when | Source today |
|---|---|---|
| `Attribute` | the node's data has the attribute's name as a key; the `value` setter runs | new private flag |
| `RelatedNode` (cardinality one, `parent`) | the node's data has the relationship's name as a key, even with `{"node": null}`; the relationship is assigned through the node | new private flag |
| `RelationshipManager` (cardinality many, `children`, `ancestors`, `descendants`) | `initialized` is true (data was given, or `fetch()` ran); the `peers` setter runs | existing `initialized`, plus a private flag for the setter |

Each attribute and cardinality-one relationship also holds a private reference to its node, bound after construction. A cardinality-many relationship reads its node from `node`, which its constructor already takes. Field objects built without a node have none.

## `is_loaded` (public, read-only property)

On `Attribute`, `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync`:

```text
is_loaded = record is true
         or the field object has no node
         or the node has no id
```

It never raises and makes no request.

## "Node from `only`" marker (private)

Kept on `InfrahubNode` and `InfrahubNodeSync`. It is a small frozen value with:

- `only`: the `only` list of the query that returned the node, as a tuple;
- `peer_of`: `None` for the queried nodes, or `"Kind.relationship"` for a peer returned with them.

Set by `_process_nodes_and_relationships` when the query had `only`:

- on each queried node;
- on each peer node built from the same response (research R9).

Peers from `fetch(only=...)` get their own marker, because they come from `filters`. Nodes built any other way have no marker and never raise `FieldNotLoadedError`.

## Server HFID (private)

Kept on `InfrahubNode` and `InfrahubNodeSync` that come from a query with `only`, when the node's data contained `hfid`, which the query requests only when `only` names it: the list the server returned, empty for a null value. It is set together with the marker. `get_human_friendly_id` returns it, or `None` when it is empty, instead of calculating the HFID. Nodes not from `only`, and peers returned with them, never have it (research R5).

## Error types (public)

All three are in `infrahub_sdk/exceptions/base.py`, subclass `Error` only, and are exported from `infrahub_sdk.exceptions`.

| Error | Attributes | Raised when |
|---|---|---|
| `FieldNotLoadedError` | `kind`, `field`, `only`, `peer_of` | a raising accessor (contract table) reads a field that is not loaded, on a node with the marker |
| `FieldNotFoundError` | `kind`, `field` | a name in `only` is not accepted for the kind (or for one of the peer kinds in `RelationshipManager.fetch`) |
| `FieldSelectionConflictError` | none | `only` is passed with `include` or `exclude` that is not `None` |

## State transitions of a field on a node from `only`

```text
not loaded --(value assigned / relationship assigned / peers assigned)--> loaded
not loaded --(RelationshipManager.fetch())--> loaded            (cardinality many only)
loaded     --(nothing makes a field not loaded again)
```

A new node (no `id`) has every field loaded. After saving, the node has an `id`. From then on, fields whose record is false report `is_loaded == False`. Reading them raises only if the node has the marker; a new node never has it.

## Store

The store is unchanged. Nodes from `only` and peers built for them (research R9) go into it as today when `populate_store` is on. The most recent copy wins lookups by `id` (`store.py:47-60`).
