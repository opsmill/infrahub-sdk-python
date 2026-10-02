# Implementation Plan: Field Selection with `only` and Known-State Field Access

**Branch**: `field-selection-only-infp-532` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/infp-532-field-selection-only/spec.md`

## Summary

Add an `only` parameter to the node query methods and to peer hydration. It replaces the default field set with exactly the named fields plus an identity floor. Alongside it, give every attribute and relationship a known state (`is_loaded`), following one rule: present in the data, assigned since, or the node has no `id`.

Reading a field the SDK doesn't know emits a `FieldNotLoadedWarning` (a `FutureWarning`) in 1.x and raises `FieldNotLoadedError` once a single private switch is flipped for 2.0. Nodes produced by `only` raise from the first release.

Under `only`, the queried node's envelope leaves out `hfid` unless it's named; default queries are unchanged. First-party narrowing call sites move to `only`, and CLI rendering and the importer skip unknown fields.

The technical approach (details in [research.md](research.md)):

- Shared, pure selection-decision helpers used by both the async and sync query generators.
- A `Selection` record bound to nodes by `client.filters`.
- Presence flags on field objects with an owner back-reference.
- A `ContextVar` that keeps the SDK's own reads silent.

## Technical Context

**Language/Version**: Python 3.10–3.13

**Primary Dependencies**: pydantic >= 2.0, httpx, graphql-core (existing; no new dependencies)

**Storage**: N/A (in-memory node state only)

**Testing**: pytest (asyncio auto mode), pytest-httpx for unit tests, testcontainers for integration; `ty` and `mypy` for types

**Target Platform**: Any platform the SDK supports (library)

**Project Type**: Library with a CLI (`infrahubctl`)

**Performance Goals**: The known-state check adds O(1) work per field read. A narrowed query's size depends only on the named fields (SC-008).

**Constraints**:

- Async/sync parity.
- No change to positional parameter order (new parameters are appended).
- No new public configuration.
- Warnings must be visible by default and de-duplicated per call site.

**Scale/Scope**: About 8 SDK modules touched (`node/node.py`, `node/attribute.py`, `node/related_node.py`, `node/relationship.py`, `client.py`, `exceptions.py`, `query_groups.py`, `transfer/importer/json.py`), 2 new modules (`node/selection.py`, `node/field_access.py`), 4 CLI modules (`ctl/generator.py`, `ctl/check.py`, `ctl/formatters/{base,yaml}.py`, `ctl/object/update.py`), one docs guide, regenerated SDK reference docs, and three changelog fragments.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Async/Sync parity | `only`, hydration parameters, `is_loaded`, warnings and errors are identical on both clients. Selection decisions live in shared helpers, so the rules can't drift. `test_validate_method_signature` and `test_method_count` stay green, and every behavioural test runs on both clients. | ✅ Pass |
| II. Backward compatibility | `only` is additive and appended last in every signature. Reading unfetched fields follows the deprecation path: a visible warning in 1.x, an error only in 2.0 via one switch. Default queries generate exactly today's query, envelope `hfid` included, because the raw payload is observable through `get_raw_graphql_data()`, export files and Ansible module output. The API-signature change is an "ask first" gate, approved by the maintainer during grilling. | ✅ Pass |
| III. Layered architecture | All selection, known-state and validation logic lives in the SDK. The CLI only changes its call sites and skips unknown fields when rendering. | ✅ Pass |
| IV. Type safety and typed errors | Three new direct `Error` subclasses and one `FutureWarning` subclass. Full type hints. No new type-check suppressions are planned. | ✅ Pass |
| V. Test-first | Selection and access matrices with concrete assertions on both clients. A regression test for HFID, store and save on partial nodes. The suite treats `FieldNotLoadedWarning` as an error. | ✅ Pass |
| VI. Format and lint | `uv run invoke format lint-code` and `lint-docs` before each commit. | ✅ Pass |
| VII. Documentation accuracy | The `query_data.mdx` corrections (the `include` peer behaviour, the `exclude` example, the unfetched cardinality-many example) and the new sections ship in the same PR. `docs-generate` is run and `docs-validate` passes. | ✅ Pass |

**Post-design re-check**: still passes. The design adds no dependencies, no configuration and no generated-code edits. `protocols.py` is untouched, because `is_loaded` lives on the field classes, not on generated protocols.

## Project Structure

### Documentation (this feature)

```text
specs/infp-532-field-selection-only/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── public-api.md    # Phase 1
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
infrahub_sdk/
├── exceptions.py                 # + FieldNotLoadedError, SelectionFieldNotFoundError,
│                                 #   SelectionConflictError, FieldNotLoadedWarning
├── client.py                     # get/all/filters (+ overloads, both clients): `only`, conflict check,
│                                 #   validation, Selection binding; get_list_repositories → only
├── query_groups.py               # get_group → only=["members"]
├── node/
│   ├── selection.py              # NEW: Selection, IDENTITY_FLOOR_NAMES, conflict check,
│   │                             #   validate_only, selection-decision helpers
│   ├── field_access.py           # NEW: _STRICT_FIELD_ACCESS switch, internal-access ContextVar +
│   │                             #   context manager/decorator, report_unloaded_read, stacklevel helper
│   ├── node.py                   # init presence binding; query generation via shared helpers; envelope
│   │                             #   without hfid under only; Selection propagation to peers; internal-access wrapping
│   ├── attribute.py              # presence flag, owner, is_loaded, detected `value` getter
│   ├── related_node.py           # presence flag, owner, is_loaded, detected accessors, fetch(only, exclude)
│   └── relationship.py           # peers property over _peers, is_loaded, detected accessors,
│                                 #   fetch(only, exclude), re-query with only=[name]
├── transfer/importer/json.py     # skip unknown cardinality-many relationships
└── ctl/
    ├── generator.py              # only=["members"]
    ├── check.py                  # only=["members"]
    ├── formatters/base.py        # skip unknown fields
    ├── formatters/yaml.py        # skip unknown fields
    └── object/update.py          # internal access around relationship application

tests/
├── unit/sdk/test_node_selection.py      # NEW: selection matrix (query shape, validation, generics, hierarchy)
├── unit/sdk/test_node_field_access.py   # NEW: access matrix (FR-018 table, warn/strict, messages, is_loaded)
├── unit/sdk/test_node.py                # regression for partial node HFID/store/save
├── unit/sdk/test_client.py              # signature parity (existing), conflict/validation before request
├── unit/sdk/test_group_context.py       # query groups under only
├── unit/ctl/                            # formatter skips unknown fields; generator/check lookups
└── integration/test_node.py             # live: only=["name"], strict read, hydration with only

docs/docs/python-sdk/guides/query_data.mdx    # new sections + corrections
docs/docs/python-sdk/sdk_ref/**               # regenerated
changelog/+infp-532-*.md                      # added / deprecated / changed fragments
pyproject.toml                                # filterwarnings: error::...FieldNotLoadedWarning
```

**Structure Decision**: The existing single-package layout is kept. The two new modules sit in `infrahub_sdk/node/` beside the field classes they serve. New test files hold the two matrices so they're reviewable on their own. Existing test files get the targeted updates.

## Implementation Phases (for /speckit-tasks)

1. **Foundations**: the exception and warning types, `field_access.py` (switch, internal-access flag, reporting, stack level), `selection.py` (Selection, conflict check, validation, decision helpers), and the pytest `filterwarnings` entry. Add the filter early and inventory the existing tests it trips, so test churn is sized before the user stories land.
2. **User Story 1 (known state and warnings)**: presence binding in `_init_attributes` and `_init_relationships` on both node classes; `is_loaded` and detected accessors on the three field classes; `peers` as a property; internal-access wrapping of node internals; CLI formatters and importer skips. Tests: the access matrix and internal-read regression.
3. **User Story 2 (`only`)**: the parameter on the query methods and helpers (appended, with overloads); conflict check; validation including generics and fragments; query generation through shared helpers; envelope without `hfid` under `only` (unless named); Selection binding (parent bound right after `from_graphql`, before `_process_relationships` builds peers) and peer propagation; store rule for floor-only peers; the `RelatedNode.get()` store-miss hint (FR-026); FR-032 query-site migrations. Tests: the selection matrix, SC-004 (default queries byte-identical), SC-008.
4. **User Story 3 (hydration)**: `fetch(only, exclude)` on both relationship types and both clients; one-off validation against the declared peer kind; per-kind filtering. Tests: hydration cases, including heterogeneous peers.
5. **User Story 4 (strict switch)**: tests that flip `_STRICT_FIELD_ACCESS` and re-run the access matrix.
6. **Polish**: docs guide and regeneration, changelog fragments, integration tests, format, lint and type checks. Integration tests need Docker (testcontainers). If they can't run, report them as "not run" rather than "passed".

## Rollout

- The 1.x release notes explain the warning, the fix path and the 2.0 plan, and ask first-party consumers (the Infrahub server, the Ansible collection, `infrahub-sync`) to run their test suites with `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning` to size the 2.0 impact. The server's pytest configuration doesn't escalate warnings, so the SDK bump won't break its CI.
- Rolling back means pinning the previous SDK release. Default queries are unchanged, so the only runtime differences are the warnings, the new parameters, and CLI rendering skipping fields that weren't fetched.

## Complexity Tracking

No constitution violations to justify.
