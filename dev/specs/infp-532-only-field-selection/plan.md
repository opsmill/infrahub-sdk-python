# Implementation Plan: Fetch Only the Named Fields with `only`

**Branch**: `ds/infp-532-only-field-selection` | **Date**: 2026-10-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/infp-532-only-field-selection/spec.md`

## Summary

Developers get an `only=[...]` parameter on `get()`, `all()` and `filters()` on both clients, and on `fetch()` on both relationship classes. A query with `only` requests `id`, `display_label` and `__typename` plus the named fields, and nothing else, so it stays the same when the schema grows. Nodes from such a query raise `FieldNotLoadedError` when the code reads a field they do not carry. Every attribute and relationship gets an `is_loaded` property, and three new error types are added. Queries without `only` do not change.

Technical approach (details and alternatives in [research.md](./research.md)):

1. **Signatures** (R1): `only: list[str] | None = None` is appended as the last named parameter of `get`, `all` and `filters`, in every overload and implementation, on both clients. The public `generate_query_data*` methods do not change.
2. **Checks before any request** (R2, R3): the conflict check is the first statement of `get`, `all` and `filters`. `filters` checks the names against the kind's schema after resolving it and before generating the data query. For generic kinds the check includes every implementing kind's schema, read from the same branch's cache.
3. **Query generation** (R4, R5, R14): new private methods on both node classes build the query for `only`, and `filters` calls them when `only` is not `None`. The existing generators are not touched.
   - The node requests `id`, `display_label`, `__typename`, without `hfid`.
   - Named attributes are requested, and named relationships as references.
   - With `prefetch_relationships`, the peers of named relationships get their default fields.
   - Hierarchy fields are requested only when named, and then follow the same rules as other named relationships.
   - `hfid` is replaced by the kind's HFID paths, using each implementing kind's own HFID for generic kinds.
   - For generic kinds, names not on the generic go in `...on Kind` blocks under the existing alias form, with or without `fragment=True`.
4. **Recording what the response contained** (R6): every field object records whether its node's data contained it, and holds a private reference to its node. `is_loaded` combines that record with "the field was assigned" and "the node has no `id`".
5. **Raising** (R7): nodes built from an `only` response, and the peers built with them, carry a private marker holding the `only` list. The accessors listed in the [contract](./contracts/public-api.md) raise `FieldNotLoadedError` when the field is not loaded and the node has the marker.
6. **SDK reads that must not raise** (R8): saving, upserting, HFID calculation and storing read private storage at a short list of places. `RelationshipManager.peers` becomes a property backed by `_peers`.
7. **Peer nodes** (R5, R9): under `only`, peer nodes are built from the response with aliases removed, and only for:
   - named relationships with `prefetch_relationships` (for hierarchy fields, the same peers today's prefetch builds: `parent` and `children`);
   - HFID paths through a relationship.

   They go to the store. HFID peers are also kept in a private slot on their node, so `node.hfid` does not depend on the store.
8. **`fetch(only=...)`** (R10): `RelatedNode.fetch` passes `only` to `client.get`. When the cached peer is from `only` and its HFID cannot be calculated, `RelatedNode.hfid` keeps the reference's server value. `RelationshipManager.fetch` runs its checks in this order:
   - checks the names against the declared peer kind before any request;
   - reloads a relationship that is not loaded (on nodes from `only`, with `get(..., only=[name], populate_store=False)`);
   - checks every actual peer kind before adding any query to the batch.
9. **Errors and typing** (R11, R12): `FieldNotLoadedError`, `FieldNotFoundError` and `FieldSelectionConflictError` in `exceptions/base.py`, registered where the public-name tests expect them. `is_loaded` is added to the `Attribute` and `RelatedNodeBase` protocols.
10. **Docs** (R16): a section on `only` in the query guide, regenerated reference pages and a changelog fragment.

## Technical Context

**Language/Version**: Python 3.10–3.13

**Primary Dependencies**: pydantic >=2.0, httpx, graphql-core (no new dependency)

**Storage**: N/A. The in-memory client store is used as today.

**Testing**: pytest with async auto mode, pytest-httpx (`httpx_mock`), testcontainers for integration tests

**Target Platform**: Library used by integrations, generators, transforms, `infrahubctl` and the Infrahub Ansible collection

**Project Type**: Single Python library with an async and a sync client

**Performance Goals**: A query with `only` is smaller than the default query for the same kind. No extra request is added: the name check uses the schema the client already loads, and the cache serves the schemas of implementing kinds.

**Constraints**:

- Queries without `only` are unchanged (SC-003).
- The async and sync clients behave the same (constitution I).
- No new dependency.
- `protocols.py` and `catalogue.py` are generated and are not edited.
- The parameter goes last for positional callers.

**Scale/Scope**:

- `infrahub_sdk/client.py`: 3 methods × 2 clients, 20 overloads.
- `infrahub_sdk/node/`: `node.py`, `attribute.py`, `related_node.py`, `relationship.py`, and one new private helper module.
- `infrahub_sdk/exceptions/`: 3 classes.
- `infrahub_sdk/protocols_base.py`: 2 protocols.
- Tests, query guide, generated reference and changelog.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against `dev/constitution.md` (version 1.0.0).

| Principle | Status | How the plan meets it |
|---|---|---|
| I. Async/sync parity | Pass | Every new parameter, property and error is on both clients and both relationship classes. The node query generators exist in both node classes. Shared decisions (name check, HFID expansion, names to request) go in one private helper module used by both. Tests are parametrised over `client_type`. |
| II. Backward compatibility | Pass | Additive: `only` goes last and defaults to `None`. Existing queries are pinned by the unedited query-generation tests (SC-003). For nodes not from `only`, nothing raises. `is_loaded` is new. The public-API change was approved in the product review (spec, Governance Gates Crossed). |
| III. Layered architecture | Pass | All logic is in the SDK. `infrahub_sdk/ctl/` is not changed. |
| IV. Type safety and typed errors | Pass | Three new subclasses of `Error`, each with one base class as the SDK's tests require. All signatures are typed. `is_loaded` is added to the protocols in `protocols_base.py`. |
| V. Test-first | Pass | Tests are written before the code they cover (see tasks), on both clients, with concrete expected values and `match=` on every `pytest.raises`. Integration tests run against a real server. |
| VI. Format and lint | Pass | `uv run invoke format lint-code` and `uv run invoke lint-docs` are tasks before each commit. |
| VII. Documentation accuracy | Pass | The query guide and the generated reference are updated in the same pull request. The `only` section describes `only` only. |

**Result**: Pass, with no exceptions to justify. Rechecked after design: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/infp-532-only-field-selection/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions R1–R17
├── data-model.md        # Phase 1: parameter, records, marker, errors
├── quickstart.md        # Phase 1: how to check the feature works
├── contracts/
│   └── public-api.md    # Phase 1: signatures, reads that raise, errors
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
infrahub_sdk/
├── client.py              # EDIT: only on get/all/filters (all overloads, both clients); conflict check;
│                          #       name check in filters; marker on nodes and peers in
│                          #       _process_nodes_and_relationships; peer processing limited under only
├── node/
│   ├── _only.py           # ADD (private helpers): names to request for a kind, HFID expansion,
│   │                      #       name check for a kind and its implementing kinds
│   ├── node.py            # EDIT: private only-query methods (both node classes), reusing the
│   │                      #       existing peer and hierarchy helpers; HFID peer slot;
│   │                      #       field record and owner binding in _init_attributes / _init_relationships;
│   │                      #       non-raising HFID path; marker attribute; _process_relationships name filter
│   ├── attribute.py       # EDIT: is_loaded; record flag; raising value getter; internal reads use _value
│   ├── related_node.py    # EDIT: is_loaded; raising accessors; initialized reads private state;
│   │                      #       fetch(only=...) on both classes
│   └── relationship.py    # EDIT: is_loaded; peers property backed by _peers; raising accessors;
│                          #       fetch(only=...) with a check of every peer kind first (both classes)
├── exceptions/
│   ├── base.py            # EDIT: FieldNotLoadedError, FieldNotFoundError, FieldSelectionConflictError
│   └── __init__.py        # EDIT: export the three errors
└── protocols_base.py      # EDIT: is_loaded on the Attribute and RelatedNodeBase protocols

tests/
├── fixtures/error_catalogue/public_names.json   # EDIT: the three new names
├── unit/sdk/
│   ├── test_node_only_helpers.py   # ADD: name check, conflict check, HFID expansion
│   ├── test_node_only_query.py     # ADD: query generation under only (both clients)
│   ├── test_node_only_access.py    # ADD: reads that raise, is_loaded, operations that must not raise
│   ├── test_client_only.py         # ADD: get/all/filters checks and nodes from only (httpx_mock)
│   ├── test_relationship_only.py   # ADD: fetch(only=...) on both relationship classes
│   └── test_exceptions.py          # EDIT: messages of the three errors
└── integration/
    └── test_node_only.py           # ADD: animal schema, both clients

docs/docs/python-sdk/
├── guides/query_data.mdx           # EDIT: section on only, is_loaded, fetch(only=...)
└── sdk_ref/infrahub_sdk/           # REGENERATED: client.mdx, node/*.mdx

changelog/+only-field-selection.added.md   # ADD
```

**Not changed**: `infrahub_sdk/ctl/`, `infrahub_sdk/transfer/`, `infrahub_sdk/query_groups.py`, `infrahub_sdk/protocols.py`, `infrahub_sdk/exceptions/catalogue.py`, and every existing query-generation test.

**Structure Decision**: the existing single-library layout. The new private module `infrahub_sdk/node/_only.py` holds the decisions both node classes and both clients share, so the async and sync code cannot drift (constitution I). It has no public names and is not re-exported.

## Design Notes

- **Two paths in query generation**: the query for `only` is built by new private methods, and `filters` picks them when `only` is not `None`. The public generators and their bodies stay as they are. That is the simplest way to keep SC-003, because the default path is not touched.
- **No I/O in `_only.py`**: the helpers take schemas that the caller has already looked up and return plain data. The async and sync code look the schemas up with their own client and then call the same helpers.
- **Owner binding**: field objects get a private `_bind(node, present)` call after construction in `_init_attributes` and `_init_relationships`, so the public constructors keep their signatures.
- **Marker and message**: the marker is a frozen dataclass with `only` (tuple) and `peer_of` (`"Kind.relationship"` or `None`). `FieldNotLoadedError` is built from the marker, the node's kind and the field name.
- **Order in `filters`**: conflict check → schema lookup (existing) → name check → query generation (existing call, plus `only`) → requests → node building with marker → store. In `get`, the conflict check comes before its own schema lookup.
- **HFID peers**: peers built for an HFID path are stored (when `populate_store` is on) and also kept in a private slot on their node, which only the HFID calculation reads (R5). So `node.hfid` works with `populate_store=False`, the node is indexed by HFID when it is stored, and later writes to the store do not change it.
- **Existing issues found and left alone**:
  - `RelationshipManager.fetch()` on a manager that is not loaded stores the reloaded, partial parent.
  - `_process_relationships` stores reference-only peers when `include` names any relationship.
  - The fragment loop reads implementing kinds' schemas from the default branch.
  - `ancestors.fetch()` and `descendants.fetch()` raise `ValueError` on nodes not from `only` when those fields are not loaded (`relationship.py:245-246`).

  Fixing them would change behaviour outside `only`. They are listed for a follow-up.

## Complexity Tracking

No constitution violations to justify.
