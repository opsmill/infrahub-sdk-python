# Implementation report: Reference generic peers by HFID in object files

**Status**: DONE

- **Spec directory**: `specs/002-generic-peer-hfid`
- **Branch**: `atg/strict-waves-stop`
- **Base commit**: `9b79e4a9` (spec, plan and tasks)
- **Head commit**: `b5a6ae88` (review fixes); this report is committed after it
- **Wall-clock time**: about 40 minutes (08:49Z to 09:30Z on 2026-10-19)

## 1. Chunk ledger

| # | Chunk | Tasks | Outcome | Commit | Notes from the subagent |
|---|-------|-------|---------|--------|-------------------------|
| 1 | Phase 1: Setup | T001–T002 | 2 done | `6ac2567d` | `TestingNoHfid` added to the generic's `used_by` so the "no HFID" error can be tested. `device` set as required in the test schemas. |
| 2 | Phase 2: Foundational | T003–T005 | 3 done | `7b08db30` | The declared peer schema is always read (from the client cache). A single `{kind, hfid}` dict on a cardinality-many relationship now reports the "Invalid structure" message. |
| 3 | Phase 3: User Story 1 | T006–T011 | 6 done | `7f66e483` | `normalize_kind_hfid_reference` always returns a list, including for a UUID-like string, because a value under `hfid` is an HFID. The test fixture `generic_peer_subinterfaces01.yml` contains three YAML documents. |
| 4 | Phase 4: User Story 2 | T012–T017 | 6 done | `5570ff47` | Per-reference handling moved into `_clean_reference` to stay under the complexity limit. The integration tests were not observed failing before the code was written. |
| 5 | Phase 5: User Story 3 | T018–T019 | 2 done | `0f2fc46a` | A mapping without `kind` is rejected. `hfid` values must be strings. `peer_used_by` is filled for every generic peer. |
| 6 | Phase 6: Polish | T020–T025 | 6 done | `052cbb9c` | See T025 in section 6. |
| — | Review fixes | — | — | `b5a6ae88` | See section 5. |

## 2. Tasks not completed

None. All 25 tasks are marked `[X]` in `tasks.md`.

## 3. Local-pass evidence

All runs were on local macOS with Python 3.13 and uv. Integration runs used Docker with infrahub-testcontainers 1.11.5.

| Test ID | Type | Run command | Passed at | Environment | Pass line |
|---------|------|-------------|-----------|-------------|-----------|
| `tests/integration/test_spec_object.py::TestSpecObjectGenericPeer::test_schema_loaded` | integration | `uv run pytest tests/integration/test_spec_object.py -k GenericPeer -v` | 2026-10-19T08:52:45Z | Docker, testcontainers 1.11.5 | `test_schema_loaded PASSED` |
| `tests/unit/sdk/spec/test_object.py::test_get_relationship_info_generic_peer_without_hfid` | unit | `uv run pytest "tests/unit/sdk/spec/test_object.py::test_get_relationship_info_generic_peer_without_hfid" "tests/unit/sdk/spec/test_object.py::test_get_relationship_info_kind_hfid_reference" -q` | 2026-10-19T08:54:43Z | n/a | `3 passed in 0.04s` |
| `tests/unit/sdk/spec/test_object.py::test_get_relationship_info_kind_hfid_reference[one_kind_hfid\|many_kind_hfid]` | unit | same as above | 2026-10-19T08:54:43Z | n/a | `3 passed in 0.04s` |
| `tests/unit/sdk/spec/test_object.py::test_kind_hfid_reference_in_object_loading[one_physical_interface\|one_port_channel_interface\|many_mixed_kinds\|one_string_hfid_becomes_list]` | unit | `uv run pytest <node ids> -v` | 2026-10-19T08:59:56Z | n/a | `5 passed in 0.05s` |
| `tests/unit/sdk/spec/test_object.py::test_related_node_graphql_payload[kind_hfid_dict_payload]` | unit | same as above | 2026-10-19T08:59:56Z | n/a | `5 passed in 0.05s` |
| `tests/integration/test_spec_object.py::TestSpecObjectGenericPeer::test_load_with_kind` | integration | `uv run pytest tests/integration/test_spec_object.py -k GenericPeer -v` | 2026-10-19T08:59:47Z | Docker, testcontainers | `2 passed, 12 deselected in 87.66s` |
| `tests/unit/sdk/spec/test_object.py::test_hfid_only_reference_to_generic_peer_resolves_single_match` | unit | `uv run pytest tests/unit/sdk/spec/test_object.py -v -k hfid_only` | 2026-10-19T09:03:37Z | n/a | `... PASSED` |
| `tests/unit/sdk/spec/test_object.py::test_hfid_only_reference_to_generic_peer_ambiguous` | unit | same as above | 2026-10-19T09:03:37Z | n/a | `... PASSED` |
| `tests/unit/sdk/spec/test_object.py::test_hfid_only_reference_to_generic_peer_no_match[two_parts\|one_part_no_candidate]` (expected message added during review) | unit | `uv run pytest tests/unit/sdk/spec/test_object.py -v -k "nested_object_uses_named_kind or missing_hfid or no_match"` | 2026-10-19T09:26:13Z | n/a | `5 passed, 46 deselected in 0.05s` |
| `tests/integration/test_spec_object.py::TestSpecObjectGenericPeer::test_load_hfid_only` | integration | `uv run pytest tests/integration/test_spec_object.py -k GenericPeer -v` | 2026-10-19T09:03:41Z | Docker, testcontainers | `test_load_hfid_only PASSED` |
| `tests/integration/test_spec_object.py::TestSpecObjectGenericPeer::test_load_hfid_only_ambiguous` | integration | same as above | 2026-10-19T09:03:41Z | Docker, testcontainers | `test_load_hfid_only_ambiguous PASSED` |
| `tests/unit/sdk/spec/test_object.py::test_validate_format_invalid_kind_hfid_reference[kind_not_inheriting\|kind_unknown\|kind_without_hfid\|wrong_hfid_length\|extra_key\|missing_kind\|many_ref_item]` | unit | `uv run pytest tests/unit/sdk/spec/test_object.py -v -k "validate_format_invalid_kind_hfid_reference or validate_format_valid_kind_hfid_reference"` | 2026-10-19T09:07:54Z | n/a | `8 passed, 40 deselected in 0.06s` |
| `tests/unit/sdk/spec/test_object.py::test_validate_format_valid_kind_hfid_reference` | unit | same as above | 2026-10-19T09:07:54Z | n/a | `8 passed, 40 deselected in 0.06s` |
| `tests/unit/sdk/spec/test_object.py::test_validate_format_invalid_kind_hfid_reference[missing_hfid]` (review) | unit | `uv run pytest tests/unit/sdk/spec/test_object.py -v -k "nested_object_uses_named_kind or missing_hfid or no_match"` | 2026-10-19T09:26:13Z | n/a | `[missing_hfid] PASSED` |
| `tests/unit/sdk/spec/test_object.py::test_get_relationship_info_nested_object_uses_named_kind_schema[kind_in_used_by\|kind_outside_used_by]` (review) | unit | same as above | 2026-10-19T09:26:13Z | n/a | `[kind_outside_used_by] PASSED` |

Full runs after the review fixes:

- `uv run pytest tests/unit/sdk/spec/ tests/unit/ctl/object/ -q` at 2026-10-19T09:26Z: `104 passed, 4 warnings in 1.18s`
- `uv run pytest tests/integration/test_spec_object.py -k GenericPeer -q` at 2026-10-19T09:29:06Z: `4 passed, 12 deselected in 165.05s`
- Before the review fixes, `uv run pytest tests/integration/test_spec_object.py -q` at 2026-10-19T09:14:54Z: `16 passed in 425.04s`

The review regression tests were run against the code before the fix and failed (`4 failed, 1 passed`), then passed after it.

## 4. Review findings

Three reviewers covered six aspects: code, errors and types; tests and comments; and simplification.

| Severity | File | Summary | Status |
|----------|------|---------|--------|
| High (tests) | `infrahub_sdk/spec/object.py:176` | A nested `kind`+`data` object whose `kind` is not in the generic's `used_by` used the generic's schema instead of the named kind's. No test covered nested objects on generic peers. | Fixed in `b5a6ae88`: the named kind's schema is used again for nested objects, and a regression test was added. |
| Medium | `object.py:164`, docs line 226 | A reference with only `kind` reported "must be a dict with 'data'", while the docs say both keys are required. | Fixed: such a mapping is now a reference and gets the "both are required" error. Test added. |
| Low | `object.py:546` | When no inheriting kind has an HFID of the right length, the error ended with "among []". | Fixed: the message now says that no kind has an HFID with that number of values. Docs updated. |
| Medium | `object.py:538` | HFID-alone lookup makes one query per candidate kind per reference, with no cache. | Deferred. Noted in a `ponytail:` comment. Add a cache if large files become slow. |
| Medium | `tests/integration/test_spec_object.py:333,344` | The HFID-alone integration tests depend on data created by `test_load_with_kind`, so they fail when run alone. | Deferred. The file's other test classes use the same ordered pattern. |
| Medium | tests | No test for a UUID string on a generic peer without an HFID. No test for an `hfid` that is not a string or list. No integration test for a cardinality-many list of `{kind, hfid}` references. | Deferred. |
| Low | `object.py:544` | For cardinality many, the HFID-alone error position does not include the item index. | Deferred. |
| Low | `object.py:509` | A non-UUID string reference to a generic without an HFID used to be sent as an `id`, and is now resolved as an HFID. The server's handling of non-UUID IDs for generic peers was not confirmed. | Deferred. Recorded for the pull request description. |
| Low | `object.py:63` and tests | Simplifications: `normalize_hfid_references` is no longer called; string-to-list conversion of HFIDs is repeated three times; test helpers duplicate `_patch_hfid_lookup`. About 30 lines could be removed. | Deferred. `normalize_hfid_references` is a module-level function, so it was kept. |
| Low | docs | The "Reference without a kind" section does not say that a UUID string is passed through without a lookup. | Deferred. |

No critical findings.

## 5. Decisions made by the orchestrator

- The spec artifacts were committed as `9b79e4a9` before implementation, so that the review diff covers only the implementation.
- No feature branch was created, because no Jira or JPD ticket was given. All commits are on `atg/strict-waves-stop`.
- The review range was taken from the explicit `9b79e4a9..HEAD` argument instead of the changed-files detection script, which diffs against `stable` and would include unrelated history.
- The six review aspects ran as three reviewers in parallel.
- Only the high finding and two cheap findings were fixed. The other findings are listed in section 4 for a decision.
- **Server compatibility (T025)**: `RelatedNodeInput.kind` was added in Infrahub server commit `c4fa580582` (2024-11-06). The first release that contains it is 1.1.0. The compatibility page (`docs/docs/python-sdk/reference/compatibility.mdx`) lists rows back to Infrahub 0.16.x. On Infrahub 0.16.x and 1.0.x, references with `kind` and references by HFID alone to a generic peer will fail on the server. Consider adding a row to the "Feature-specific requirements" table on that page.
- `uv run invoke lint-docs` reports 20 errors in generated reference files that this change does not touch. They were left as they are.

## 6. Suggested next steps

1. Decide whether to add the Infrahub 1.1.0 minimum for this feature to `compatibility.mdx`.
2. Decide on the deferred review findings in section 4, especially the extra tests and the error position for cardinality-many items.
3. Open a pull request against `stable`. The description should mention the server version requirement and the change for non-UUID string references to generics without an HFID.
