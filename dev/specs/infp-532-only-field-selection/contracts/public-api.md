# Contract: Public API for `only`, `is_loaded` and the New Errors

**Feature**: INFP-532 | **Spec**: [../spec.md](../spec.md) | **Research**: [../research.md](../research.md)

Everything below applies to both clients. The sync classes have the same signatures and behaviour with `InfrahubClientSync`, `InfrahubNodeSync`, `RelatedNodeSync` and `RelationshipManagerSync`.

## 1. Query methods

`only` is appended as the last named parameter, after `priority` and before `**kwargs`, in every overload and in the implementation.

```python
async def get(self, kind, raise_when_missing=True, at=None, branch=None, timeout=None, id=None, hfid=None,
              include=None, exclude=None, populate_store=True, fragment=False, prefetch_relationships=False,
              property=False, include_metadata=False, query_name=None, priority=None,
              only: list[str] | None = None, **kwargs)

async def all(self, kind, at=None, branch=None, timeout=None, populate_store=True, offset=None, limit=None,
              include=None, exclude=None, fragment=False, prefetch_relationships=False, property=False,
              parallel=False, order=None, include_metadata=False, query_name=None, priority=None,
              only: list[str] | None = None)

async def filters(self, kind, at=None, branch=None, timeout=None, populate_store=True, offset=None, limit=None,
                  include=None, exclude=None, fragment=False, prefetch_relationships=False, partial_match=False,
                  property=False, parallel=False, order=None, include_metadata=False, query_name=None,
                  priority=None, only: list[str] | None = None, **kwargs)
```

Behaviour:

| Call | Result |
|---|---|
| `only=None` (or not passed) | Query and nodes exactly as today |
| `only=[...]` with `include` or `exclude` not `None` | `FieldSelectionConflictError`, no request sent |
| `only=[...]` with an unknown name | `FieldNotFoundError(kind, field)`, before the data query |
| `only=[...]` on a generic kind with `fragment=True` | Same query as without `fragment`; no default fields of implementing kinds are added |
| `only=[]` | Node requests `id`, `display_label`, `__typename` only |
| `only=["name"]` | Node requests `id`, `display_label`, `__typename`, `name { value }` |
| `only=["site"]` | Adds `site { node { id hfid display_label __typename } }` |
| `only=["site"], prefetch_relationships=True` | The `site` peer also gets its default fields; peer nodes are built and stored |
| `only=["hfid"]` | Node requests `id`, `hfid`, `display_label`, `__typename`; no field, relationship or peer that the HFID is made of. For a generic kind, `hfid` is requested when the generic or an implementing kind has an HFID |
| `only=["hfid"]` on a kind without an HFID | Same as `only=[]` |
| `only=["parent"]` on a hierarchical kind | Adds `parent` as a reference, in an inline fragment on the peer kind that the kind's schema declares for `parent`, or on the hierarchy generic when the schema declares none; no other hierarchy field. `children` works the same way; `ancestors` and `descendants` always use the hierarchy generic |
| `only=["parent"], prefetch_relationships=True` | The `parent` peer also gets the default fields of that peer kind, without its own hierarchy fields; the peer node is built and stored |
| `only=["id", "display_label"]` | Same as `only=[]` |
| Generic kind, name only on some implementing kinds | Requested in `...on Kind` blocks for those kinds, with or without `fragment=True` |

`property=True` and `include_metadata=True` keep adding their data to the named fields and the node.

`generate_query_data_init`, `generate_query_data` and `generate_query_data_node` on `InfrahubNode` and `InfrahubNodeSync` do not change. The query for `only` is built by private methods that `filters` calls.

## 2. Fetching peers

```python
# RelatedNode / RelatedNodeSync
async def fetch(self, timeout: int | None = None, priority: Priority | None = None,
                only: list[str] | None = None) -> None

# RelationshipManager / RelationshipManagerSync
async def fetch(self, only: list[str] | None = None) -> None
```

| Call | Result |
|---|---|
| `RelatedNode.fetch(only=[...])` | One `get` of the peer with `only`; the peer replaces the cached peer and goes to the store. `hfid` and `hfid_str` keep the reference's server value when the fetched peer has no HFID: its response contained no `hfid` (or an empty one) and its fields do not give one |
| `RelatedNode.fetch()` on a relationship that is not loaded, node from `only` | `FieldNotLoadedError` |
| `RelatedNode.fetch()` on a relationship with no peer, any other node | `Error`, as today |
| `RelationshipManager.fetch(only=[...])` | In this order: checks `only` against the declared peer kind (no request yet); reloads the relationship if it is not loaded; checks `only` against every actual peer kind; then one `filters(..., only=...)` per peer kind in a batch |
| Reload on a node from `only` | `get(kind, id=..., only=[relationship name], populate_store=False)`; works for `ancestors` and `descendants` |
| Reload on any other node | As today (`include` plus `exclude`) |
| A name unknown on the declared peer kind | `FieldNotFoundError`, no request sent |
| A name missing on one of the actual peer kinds | `FieldNotFoundError`, no peer query sent |

## 3. `is_loaded`

```python
@property
def is_loaded(self) -> bool
```

On `Attribute`, `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync`, and on the `Attribute` and `RelatedNodeBase` protocols in `infrahub_sdk/protocols_base.py`. It returns `True` when the response contained the field, when the field was assigned since, when the field object has no node, or when the node has no `id`. It never raises.

## 4. Reads that raise `FieldNotLoadedError`

A read raises only when the field is not loaded (`is_loaded` is `False`) **and** the node is from `only`: a node returned by a query with `only`, a peer returned with it, or a peer fetched with `fetch(only=...)`. On every other node, these reads behave as today.

| Field object | Raises on | Never raises `FieldNotLoadedError` on |
|---|---|---|
| `Attribute` | `value` | `is_loaded`, `name`, `id`, `is_default`, `is_from_profile`, `is_inherited`, `updated_at`, `is_protected`, `source`, `owner`, `updated_by` |
| `RelatedNode`, `RelatedNodeSync` (cardinality one, `parent`) | `id`, `hfid`, `hfid_str`, `display_label`, `typename`, `kind`, `peer`, `get()`, `fetch()` | `is_loaded`, `initialized`, `is_resource_pool`, `is_from_profile`, `name`, `schema`, relationship properties |
| `RelationshipManager`, `RelationshipManagerSync` (cardinality many, `children`, `ancestors`, `descendants`) | `peers`, `peer_ids`, `peer_hfids`, `peer_hfids_str`, indexing, iteration, `is_from_profile` | `is_loaded`, `initialized`, `has_update`, `name`, `schema`, `fetch()` |

Node methods that read through these accessors raise in the same cases, for example `get_path_value` and `get_flat_value`. So do `matches_local_checksum`, `download_file(skip_if_unchanged=True)` and `upload_if_changed`, when `checksum` was not fetched.

Operations that never raise on a node from `only`:

- `save()` (create and update);
- `create(allow_upsert=True)`;
- `update()`;
- `hfid`, `hfid_str`, `get_human_friendly_id()`, `get_human_friendly_id_as_string()`. When `only` named `hfid`, they return the server's value, or `None` when it is empty or null, until a field the HFID is built from is changed on the node; otherwise they are calculated from the fetched fields;
- putting the node in the store;
- `__repr__` and `__str__`.

When the HFID is calculated, every node uses the same private reader. A field that a node from `only` did not fetch counts as missing, also when the reader reaches that node as a peer in the store. Every other field is read as `get_path_value` reads it. So the HFID methods above, and putting a node in the store, do not raise on any other node either, even when a peer that the HFID reads came from `only`.

`add`, `extend` and `remove` on a cardinality-many relationship that is not loaded keep raising `UninitializedError`, as today.

## 5. Errors

All in `infrahub_sdk.exceptions`, each with `Error` as its only base class.

```python
class FieldNotLoadedError(Error):
    def __init__(self, kind: str, field: str, only: Sequence[str], peer_of: str | None = None) -> None: ...
    # message: "InfraDevice.description was not fetched: the node was queried with only=['name']. Add 'description' to only, or check is_loaded before reading it."
    # with peer_of: "InfraSite.description was not fetched: the node is a peer of InfraDevice.site, queried with only=['site']. ..."

class FieldNotFoundError(Error):
    def __init__(self, kind: str, field: str) -> None: ...
    # message: "'nmae' is not an attribute or relationship of InfraDevice."

class FieldSelectionConflictError(Error):
    def __init__(self) -> None: ...
    # message: "only cannot be combined with include or exclude."
```

The exact wording is set during implementation. The tests match on the kind, the field and the `only` list.
