# Implementation Report: Fetch Only the Named Fields with `only`

**Status**: ✅ DONE

| Item | Value |
|---|---|
| Spec directory | `dev/specs/infp-532-only-field-selection` |
| Branch | `ds/infp-532-only-field-selection` |
| Base commit (implementation start) | `89ccb4a5` |
| Head commit (code) | `0be31de9` |
| Wall-clock | 2026-10-14 21:14 UTC → 2026-10-15 00:51 UTC (about 3 h 40 min) |
| Tasks | 34 of 34 `[X]` |
| Final unit suite | `tests/unit/`: 2830 passed, 2 skipped, 1 xfailed, 8 failed (environmental, see §6) |
| Final integration run | `tests/integration/test_node_only.py`: 14 passed against Infrahub 1.11.5 |

## 1. Summary

The SDK accepts `only=[...]` on `get`, `all` and `filters` (async and sync) and on `fetch` of `RelatedNode`, `RelatedNodeSync`, `RelationshipManager` and `RelationshipManagerSync`.

- A query with `only` requests `id`, `display_label`, `__typename` and the named fields, and no other field of the kind.
- `hfid` in `only` is replaced by the fields of the kind's human-friendly ID. For a generic kind, each implementing kind's own HFID applies.
- Reading a field that a node from `only` (or a peer returned with it) did not fetch raises `FieldNotLoadedError`.
- Every attribute and relationship has `is_loaded`.
- `FieldNotFoundError` and `FieldSelectionConflictError` are raised before the data query.
- Saving, upserting, the HFID and the store do not raise on nodes from `only`.
- Queries without `only` are unchanged: no existing query-generation test was edited, and nodes not from `only` never raise the new error.

## 2. Chunk ledger

| # | Chunk | Tasks | ✅ / ⚠️ / ❌ | Commits | Flagged upward |
|---|---|---|---|---|---|
| 1 | Phase 1 Setup (T001) | 1 | 1 / 0 / 0 | none (run by the orchestrator) | The `infrahub_testcontainers` pytest plugin crashes at session start on this Mac; every run disables it. |
| 2a | Phase 2: errors and helpers (T002, T003, T005, T006) | 4 | 4 / 0 / 0 | `a5f7fefc`, `dc7075df` | A generic kind accepts hierarchy names when it is hierarchical or any implementing kind is. Wrote the peer hint of `FieldNotLoadedError` (later reworded in review). |
| 2b | Phase 2: record and `is_loaded` (T004, T007–T011) | 6 | 6 / 0 / 0 | `f8d589ac` | A manager's record is `initialized or peers assigned`. `peers` became a property over `_peers`; no `__len__`/`__bool__` added. |
| 3a | US1: query generation (T012, T013, T017, T018) | 4 | 4 / 0 / 0 | `e5c3efa5`, `699a2ac2`, `5d44ee59` | The first version let `prefetch_relationships` expand a relationship added only for the HFID (my briefing was ambiguous). Fixed in `5d44ee59` with schema-growth tests that fail without the fix. |
| 3b-i | US1: client wiring, peers, HFID (T014, T020, T021, T022) | 4 | 4 / 0 / 0 | `0b36b35e` | The assertion "reading an unfetched field from the store raises" was moved to 3b-ii, because it needs the raising accessors. |
| 3b-ii | US1: raising reads, safe saves (T015, T016, T019, T023) | 4 | 4 / 0 / 0 | `e5fae4ef` | No internal SDK read needed changing: save, upsert, HFID and store only read loaded fields or private storage. |
| 4 | US2: `fetch(only=...)` (T024–T026) | 3 | 3 / 0 / 0 | `4b26e7e7`, `e31263b9` | Seven deliberate breaks of the code were each caught by a test. |
| 5a | Polish: integration tests (T027) | 1 | 1 / 0 / 0 | `a4adf56c` | Each test class boots its own stack (≈3.5 min). |
| 5b | Polish: docs, changelog, checks (T028–T034) | 7 | 7 / 0 / 0 | `ef2b1617`, `71455293`, `3f24468d` | `lint-docs` exits 1 on the base commit as well (vale findings in generated pages, see §6). |
| R-A | Review fixes, code and docs | — | — | `be220357`, `e8cb0ed6` | See §5. |
| R-B | Review fixes, tests | — | — | `5cb84017`, `05092de8`, `e3ccf9ce`, `d14e41f8` | Found that the HFID of nodes outside `only` changed in one edge case; fixed in `0be31de9`. |
| R-C | Orchestrator fix | — | — | `0be31de9` | Nodes outside `only` compute their HFID with the original public lookup again. |

Chunk 3 of `tasks.md` (User Story 1, 12 tasks) was split into three chunks (3a, 3b-i, 3b-ii) along the seams "query", "nodes and peers come back right", "reads raise and SDK operations do not". The other phases ran as written.

## 3. Tasks not completed

None. All 34 tasks are `[X]`.

## 4. Local-pass evidence

Unit tests ran with `cd <repo> && env -u INFRAHUB_API_TOKEN -u INFRAHUB_ADDRESS uv run pytest <files> -rA -q -p no:cacheprovider -p no:pytest-infrahub-performance-test`. Integration tests ran with the same flags plus `DOCKER_HOST` set to the Docker Desktop socket in the user's home directory and `--no-cov`. The rows below are from the final runs on the head commit `0be31de9`. Each row is one test function; the count is the number of `PASSED` lines it produced (both clients, all cases).

| Test id | Type | Run command | Passed at (ISO 8601) | Environment context | Verbatim pass line |
|---|---|---|---|---|---|
| `tests/unit/sdk/test_node_only_helpers.py` (10 functions: conflict check, field names, name check accept/reject, peer check accept/reject, HFID expansion, marker errors) | unit | unit command on the six files below | 2026-10-15T00:48:05Z | n/a | `PASSED tests/unit/sdk/test_node_only_helpers.py::test_name_check_rejects[...]` (48 PASSED lines in the file) |
| `tests/unit/sdk/test_node_only_query.py::test_only_query` | unit | same | 2026-10-15T00:48:05Z | n/a | 64 × `PASSED tests/unit/sdk/test_node_only_query.py::test_only_query[...]` |
| `tests/unit/sdk/test_node_only_query.py::test_only_query_unchanged_when_schema_grows` | unit | same | 2026-10-15T00:48:05Z | n/a | 8 × `PASSED ...::test_only_query_unchanged_when_schema_grows[...]` |
| `tests/unit/sdk/test_node_only_query.py` (arguments, hierarchy prefetch, unknown name, name order) | unit | same | 2026-10-15T00:48:05Z | n/a | 2 × `PASSED` each |
| `tests/unit/sdk/test_client_only.py` (13 functions: conflict and unknown-name errors before any request, string `only`, request bodies, nodes and peers in store, HFID with and without store, store lookup by HFID, narrower peer, replaced copy, ignored names in include/exclude) | unit | same | 2026-10-15T00:48:05Z | n/a | 68 `PASSED` lines, e.g. `PASSED tests/unit/sdk/test_client_only.py::test_only_request_body[...]` |
| `tests/unit/sdk/test_node_only_access.py::test_read_of_a_field_not_fetched_raises` / `::test_read_of_a_fetched_field_returns_its_value` | unit | same | 2026-10-15T00:48:05Z | n/a | 34 × `PASSED` each |
| `tests/unit/sdk/test_node_only_access.py::test_hfid_of_a_default_node_is_built_from_its_path_values` | unit | same | 2026-10-15T00:48:05Z | n/a | 22 × `PASSED` (fails 2 of 22 without `0be31de9`) |
| `tests/unit/sdk/test_node_only_access.py` (27 other functions: `is_loaded` on default nodes, assignment, hierarchy, peers, file checksum checks, update/create bodies, HFID, store, mutation result, repr, edits of an unloaded relationship) | unit | same | 2026-10-15T00:48:05Z | n/a | 132 `PASSED` lines |
| `tests/unit/sdk/test_relationship_only.py` (12 functions: `RelatedNode.fetch(only=...)`, HFID after fetch, unknown names, manager fetch with mixed kinds, reload before the per-kind check, reload on a node from `only`, `ancestors`/`descendants`, markers on peers, behaviour without `only`) | unit | same | 2026-10-15T00:48:05Z | n/a | 40 `PASSED` lines |
| `tests/unit/sdk/test_exceptions.py::TestFieldSelectionErrors` (5 functions incl. serialisation) | unit | same | 2026-10-15T00:48:05Z | n/a | 34 `PASSED` lines |
| Six files above, total | unit | `... pytest tests/unit/sdk/test_node_only_helpers.py tests/unit/sdk/test_node_only_query.py tests/unit/sdk/test_node_only_access.py tests/unit/sdk/test_client_only.py tests/unit/sdk/test_relationship_only.py "tests/unit/sdk/test_exceptions.py::TestFieldSelectionErrors" -rA -q ...` | 2026-10-15T00:48:05Z | n/a | `492 passed in 4.67s` |
| `tests/integration/test_node_only.py::TestNodeOnly` (7 tests) | integration | `DOCKER_HOST=... uv run pytest tests/integration/test_node_only.py -rA ... --no-cov` | 2026-10-15T00:50:40Z | image `registry.opsmill.io/opsmill/infrahub:1.11.5` (default from `infrahub-testcontainers` 1.11.5), testcontainers stacks removed by the harness, no workaround | `PASSED tests/integration/test_node_only.py::TestNodeOnly::test_save_of_node_from_only_keeps_its_other_fields` (and the 6 others) |
| `tests/integration/test_node_only.py::TestNodeOnlySync` (7 tests) | integration | same | 2026-10-15T00:50:40Z | same | `PASSED tests/integration/test_node_only.py::TestNodeOnlySync::test_manager_fetch_with_only_reads_the_named_fields_of_each_peer_kind` (and the 6 others); `14 passed, 16 warnings in 170.95s` |

Whole unit suite on `0be31de9`: `8 failed, 2830 passed, 2 skipped, 1 xfailed`. The 8 failures are in `tests/unit/pytest_plugin/test_plugin.py`; the same 8 fail on the base commit (§6).

## 5. Review findings

Six reviewers ran in parallel on `89ccb4a5..3f24468d`: code, tests, comments and docs, error handling, type design, and simplification (report only). No critical findings.

| Severity | File | Summary | Disposition |
|---|---|---|---|
| High | `docs/.../guides/query_data.mdx` | The example schema gave `TestInterface` an HFID through `device`, which was optional; the server only accepts HFID paths through a mandatory cardinality-one relationship. | ✅ `device` made mandatory in the example (`e8cb0ed6`) |
| High | `tests/unit/sdk/test_relationship_only.py` | The "reload first" case never reloaded, so the required check order had no test. | ✅ New test; fails if the reload is skipped or the per-kind check moves before it (`05092de8`) |
| High | `query_data.mdx` | "Hierarchy fields are requested only when named" was false when the HFID goes through `parent`. | ✅ Caveat added (`e8cb0ed6`) |
| High | `related_node.py`, `relationship.py` | `fetch` docstrings said they fetch the "full" peer. | ✅ Reworded (`be220357`) |
| Medium | `client.py`, `node.py` | The field plan was computed twice per call (and names checked twice); `only` and `only_fields` passed separately; marker code duplicated in both clients. | ✅ Planned once and passed in; `only` carried in `OnlyQueryFields`; one `_mark_from_only` method (`be220357`) |
| Medium | `exceptions/base.py` | The peer error advised `fetch(only=[field])`, which would replace the peer with a narrower copy. | ✅ Hint reworded (`be220357`) |
| Medium | `exceptions/base.py` | The three new errors could not be pickled or copied. | ✅ `__reduce__` added, round-trip test (`be220357`) |
| Medium | `query_data.mdx`, `store.mdx` | "One query per peer kind" (it is a count query plus pages); store sentence incomplete. | ✅ Reworded (`e8cb0ed6`) |
| Medium | tests | Shared helpers imported from other test modules; fixture defined three times. | ✅ Moved to `tests/helpers/only_data.py` and `tests/unit/sdk/conftest.py`; test ids unchanged (`5cb84017`) |
| Medium | tests | Missing: `add`/`extend`/`remove` on a node from `only`; ignored unknown names in `include`/`exclude`; HFID path forms on default nodes; `RelatedNode.fetch` with an unknown name; manager fetch and prefetch against a real server. | ✅ Added (`05092de8`) |
| Medium | `node.py` (found while fixing) | The HFID of nodes outside `only` used the new reader; one edge case (a path without `__value` on an attribute missing from the data) gave `None` instead of the old value. | ✅ Original lookup restored for those nodes, with a test (`0be31de9`) |
| Medium | `relationship.py` | Managers keep two references to their node (`node` and `_node`). | Deferred: merging would change `is_loaded` for managers built on their own |
| Low | several | `only` given as a string; `getattr` default; class docstrings; `get` docstring; guide wording; weak `hfid_str` test cases; low-value helper tests; `Raises:` for the new `TypeError`. | ✅ Fixed (`be220357`, `e8cb0ed6`, `05092de8`, `e3ccf9ce`) |
| Low | `_only.py`, field classes | `KindFields` invariants only documented; mappings are plain dicts in frozen dataclasses; `_raise_if_not_loaded` repeated in three classes; `Any` annotations; a `getattr` marker read; peers from `fetch(only=...)` carry no `peer_of`; small repeated checks. | Deferred (maintainability only, no behaviour impact) |

## 6. Autonomous decisions

- **Setup run by the orchestrator.** T001 changes no code, so I ran it myself instead of dispatching a chunk.
- **Local test environment.** Every run disables the `pytest-infrahub-performance-test` plugin (its psutil `cpu_freq` call crashes at session start on this Mac with Python 3.14). Because of the same plugin, the 8 tests in `tests/unit/pytest_plugin/test_plugin.py`, which start inner pytest sessions, fail locally on the base commit and on every commit of this branch. CI runs on Linux and is not affected.
- **Chunk split.** User Story 1 was split into three chunks (see §2), and one assertion of T014 was moved to the next chunk.
- **Prefetch and HFID-only relationships.** My first briefing for chunk 3a was ambiguous and the chunk let `prefetch_relationships` expand a relationship added only for the HFID. I sent the same agent back to fix it against FR-004, FR-005 and SC-002 (`5d44ee59`).
- **Review triage.** I fixed every high finding, 12 of 13 medium findings and the low findings that were cheap and affected accuracy or tests. I deferred the rest (§5).
- **HFID of nodes outside `only`.** The tests pass with either behaviour, but constitution II says nothing changes for nodes outside `only`, so I restored the original lookup for them (`0be31de9`).
- **Guide example schema.** Making `TestInterface.device` mandatory changes an existing example, which is needed for the HFID example to be valid on a real server.
- **`lint-docs`.** It exits 1 on the base commit too: vale spelling findings in generated reference pages (`typename`, `accessor`, `upserted`, …) on lines this branch did not write. `docs-validate`, `rumdl`, ruff, mypy and ty pass.
- **Pushes.** The branch was pushed after the foundational phase (`f8d589ac`) and after User Story 1 (`e5fae4ef`), as agreed. The rest is not pushed yet.

## 7. Suggested next steps

1. Push the branch and open the pull request against `infrahub-develop`.
2. Decide whether to address the deferred findings in §5 in this pull request or later.
3. Follow-ups from the spec, each in its own pull request:
   - the `infrahubctl object update --set` issue on cardinality-many relationships;
   - the existing issues listed in plan.md "Design Notes" (the default reload of a manager stores a partial parent and fails on `ancestors`/`descendants`; reference-only peers stored when `include` names a relationship; the fragment loop reading the default branch's schemas).
4. Run `speckit-opsmill-extract` after the pull request is reviewed.

## 8. Changes after the pull-request review

A review of [opsmill/infrahub-sdk-python#1423](https://github.com/opsmill/infrahub-sdk-python/pull/1423) led to commit [`909a2936`](https://github.com/opsmill/infrahub-sdk-python/commit/909a293673cdb487da2e78e4e8dd1672ff9aee28). It changes the following behaviour and code:

- **HFID through `parent`.** A hierarchy field that the kind also declares as a relationship now uses the declared peer kind for its inline fragment and its peer fields. Before, the query used the hierarchy generic and left out any HFID attribute that only the parent kind has, so `node.hfid` was `None`. A peer attribute that the peer kind does not have now raises `FieldNotFoundError` instead of being left out of the query. With `prefetch_relationships`, the peers of `parent` and `children` get the default fields of the declared peer kind.
- **One HFID reader.** Every node calculates its HFID with the private reader. It replaces the split restored in `0be31de9` (§5, §6), and gives the same results as before for nodes outside `only`. It also stops a node from a default query from raising `FieldNotLoadedError` when its peer in the store came from `only`.
- **Managers keep one reference to their node.** The finding deferred in §5 is fixed: managers read `node`. The test that built a manager with a node and expected `is_loaded` to be `True` now builds it without a node.
- **Smaller changes.** The default query wraps hierarchy fields with the same helper as the query with `only`. `fetch()` passes `only` to the client only when it is set. `all()` no longer repeats the check that `filters()` runs.

The review also found that every field holds a reference to its node, which adds reference cycles (critique E12). No change was made: nodes from the default schemas were already in a cycle through their relationship managers before this branch.

Unit suite after the commit, rebased on `521e7459`: 2858 passed, 2 skipped, 1 xfailed, 8 failed. The 8 failures are the tests in `tests/unit/pytest_plugin/test_plugin.py` described in §6. The integration tests were not run again.
