# Implementation Report: Field Selection with `only` and Known-State Field Access (INFP-532)

**Status**: ✅ DONE

| Item | Value |
|---|---|
| Spec directory | `dev/specs/infp-532-field-selection-only` |
| Branch | `field-selection-only-infp-532` |
| Base commit (implementation start) | `2ac475e05373daf1d3f6ba7bbbaacfba9dccd67c` |
| Head commit | `f2d0379d` |
| Wall-clock | 2026-10-02 17:28 → 20:26 (about 3 h) |
| Tasks | 48 of 48 `[X]` |
| Final unit suite | 2556 passed, 2 skipped, 1 xfailed, 4 failed (environmental, see §6) |
| Final integration run | `tests/integration/test_node.py`: 19 passed against Infrahub 1.11.3 |

## 1. Summary

The SDK now accepts `only=[...]` on `get`, `all` and `filters` (async and sync) and on peer hydration (`RelatedNode.fetch`, `RelationshipManager.fetch`).

Every attribute and relationship exposes `is_loaded`. Reading a field the SDK never received emits `FieldNotLoadedWarning` in 1.x. It raises `FieldNotLoadedError` on nodes produced by `only`, or once the private switch `_STRICT_FIELD_ACCESS` is flipped for 2.0.

Default queries are byte-identical to before. A check across 10,560 argument combinations confirmed this, and `test_default_query_is_unchanged` pins it.

## 2. Chunk Ledger

| # | Chunk (tasks.md phase) | Tasks | ✅ / ⚠️ / ❌ | Commits | Flagged upward |
|---|---|---|---|---|---|
| 1 | Phase 1 Setup (T001–T003) | 3 | 3 / 0 / 0 | `4bf3e1d4` | Helpers are module functions, not fixtures. `std_group_schema` extended with `members` via `model_copy`. Scoped `ty` override for the new test file. |
| 2 | Phase 2 Foundational (T004–T010) | 7 | 7 / 0 / 0 | `ecd99db2`, `85af1410` | Wrote the selection-error message texts. `Selection.for_peer` is a staticmethod. `is_attribute_selected` keeps an unused `include` parameter (`noqa: ARG001`). |
| 3 | US1 core: tests and field classes (T011–T014, T016–T020) | 9 | 9 / 0 / 0 | `9b0ba7d2` | Manager `is_loaded` defined once on the base through an `_owner` property. Assigning `peers` doesn't mark a manager initialized. `_current_*` private readers give one report per read. Only 2 existing tests tripped the new filter. |
| 4 | US1 consumers: CLI and importer (T015, T021–T024) | 5 | 5 / 0 / 0 | `dcb0f92a`, `68193347` | JSON and YAML omit unknown fields, table and CSV show blanks. T024 widened a fixture instead of asserting the warning. Found an existing bug: `object update --set <many>=` sent no peers (fixed in review). |
| 5 | US2 query generation (T025, T026, T030–T033) | 6 | 6 / 0 / 0 | `6c50ae11` | Hierarchical floor kept inside the existing `...on <Kind>` fragment. New helper `implementing_kind_only`. Default-query literals were generated from pre-change code. |
| 6 | US2 client wiring, behaviour and call sites (T027–T029, T034–T038) | 8 | 8 / 0 / 0 | `5e0225b0` | Added a docstring for `get`. Private `_get_schema_for_selection` per client. Sync `get_list_repositories` raises `NotImplementedError`, so only async was migrated (later reverted, see §5). `ctl/check.py` has no unit test. |
| 7 | US3 hydration (T039–T041) | 3 | 3 / 0 / 0 | `ccececd0` | The re-query of an uninitialized manager now uses `populate_store=False`, so a narrow strict copy never replaces the stored parent. New helper `peer_kind_only`. |
| 8 | US4 strict switch (T042) | 1 | 1 / 0 / 0 | `fce79db2` | Matrices parametrised over a `strict_switch` fixture (warn and strict). Removed one test the new rows duplicate. Disabling the switch confirmed that exactly the 18 strict warn-row tests fail. |
| 9 | Phase 7 Polish (T043–T048) | 6 | 6 / 0 / 0 | `fba984fb`, `1ba6d056`, `11f62f9a`, `0d38ec3d`, `5efb0733` | `python -W error::infrahub_sdk.exceptions.FieldNotLoadedWarning` is rejected by Python ("invalid module name"), so the docs use pytest `-W` or `filterwarnings`, or `warnings.simplefilter`. Wrapped one existing integration read in `pytest.warns`. `docs-validate` runs on this host. |
| R1 | Review fixes: code and tests | — | — | `39ec860b`, `ccc1fe2e`, `0e20cdb3` | See §5. |
| R2 | Review fixes: docs, changelog, docstrings, spec | — | — | `a28cfb06`, `3ffe4033`, `f2d0379d` | See §5. Spec, contract, research and alignment check updated for the three post-implementation deviations (P1–P3). |

## 3. Tasks Not Completed

None. All 48 tasks are `[X]`.

## 4. Local-Pass Evidence

All unit rows are environment `n/a` (mocked, `httpx_mock`), run as `env -u INFRAHUB_API_TOKEN uv run pytest <ids> -v -p no:randomly --no-cov`. Parametrised IDs are grouped in braces, and every combination passed. The final two rows re-verify everything at the head commit.

| Test id | Type | Run command | Passed at (ISO 8601) | Environment context | Verbatim pass line |
|---|---|---|---|---|---|
| Entire unit suite at `f2d0379d` | unit | `env -u INFRAHUB_API_TOKEN uv run pytest tests/unit -q -p no:randomly --no-cov` | 2026-10-02T20:22:31+02:00 | n/a | `4 failed, 2556 passed, 2 skipped, 1 xfailed, 17 warnings in 38.49s` (4 failures: `/bin/bash` missing, §6) |
| `tests/integration/test_node.py` (all 19, including the 5 new or modified below) at `f2d0379d` | integration | `env -u INFRAHUB_API_TOKEN uv run pytest tests/integration/test_node.py -v --no-cov -p no:randomly` | 2026-10-02T20:25:40+02:00 | Docker 29.8.0, infrahub-testcontainers 1.11.3, image `registry.opsmill.io/opsmill/infrahub:1.11.3` | `19 passed, 16 warnings in 178.40s (0:02:58)` |
| `test_node.py::TestInfrahubNode::test_node_filters_only[{standard,sync}]` | integration | as above | 2026-10-02T20:25:40+02:00 | as above | `tests/integration/test_node.py::TestInfrahubNode::test_node_filters_only[standard] PASSED` |
| `test_node.py::TestInfrahubNode::test_node_fetch_relationship_only[{standard,sync}]` | integration | as above | 2026-10-02T20:25:40+02:00 | as above | `tests/integration/test_node.py::TestInfrahubNode::test_node_fetch_relationship_only[sync] PASSED` |
| `test_node.py::TestInfrahubNode::test_node_filters_include` (modified) | integration | as above | 2026-10-02T20:25:40+02:00 | as above | `tests/integration/test_node.py::TestInfrahubNode::test_node_filters_include PASSED` |
| `tests/unit/sdk/test_node_field_access.py::test_location_payload_builds_full_and_partial_nodes[{standard,sync}]` | unit | chunk 1 command | 2026-10-02T17:35:15+02:00 | n/a | `...::test_location_payload_builds_full_and_partial_nodes[standard] PASSED` |
| `tests/unit/sdk/test_node_selection.py::test_generic_family_resolves_from_schema_cache[{standard,sync}]` | unit | chunk 1 command | 2026-10-02T17:35:15+02:00 | n/a | `...::test_generic_family_resolves_from_schema_cache[sync] PASSED` |
| `tests/unit/sdk/test_node_hydration.py::test_group_members_resolve_from_schema_cache[{standard,sync}]` | unit | chunk 1 command | 2026-10-02T17:35:15+02:00 | n/a | `...::test_group_members_resolve_from_schema_cache[standard] PASSED` |
| `tests/unit/sdk/test_field_access.py` (all, 37 IDs incl. the review-updated `test_build_unloaded_message[7 cases]` and `test_report_unloaded_read_warning_carries_the_fetch_hint`) | unit | `... pytest tests/unit/sdk/test_field_access.py ...` | 2026-10-02T17:48:12+02:00; updated cases 2026-10-02T20:04:11+02:00 | n/a | `tests/unit/sdk/test_field_access.py::test_report_unloaded_read_warning_skips_every_sdk_frame PASSED` |
| `tests/unit/sdk/test_selection.py` (all, including 2 `implementing_kind_only` tests from chunk 5) | unit | `... pytest tests/unit/sdk/test_selection.py ...` | 2026-10-02T17:48:12+02:00; chunk-5 cases 2026-10-02T18:34:05+02:00 | n/a | `tests/unit/sdk/test_selection.py::test_validate_only_rejects_implementing_kind_names_without_fragment PASSED` |
| `tests/unit/sdk/test_exceptions.py` (all, 21 IDs) | unit | `... pytest tests/unit/sdk/test_exceptions.py ...` | 2026-10-02T17:48:12+02:00 | n/a | `tests/unit/sdk/test_exceptions.py::test_selection_errors_are_direct_subclasses_of_error[FieldNotLoadedError] PASSED` |
| `test_node_field_access.py::test_attribute_value_read[{warn,strict}-{standard,sync}-{present-with-value,present-with-null-value,absent-on-node-with-id,absent-on-node-without-id}]` | unit | `... pytest tests/unit/sdk/test_node_field_access.py ...` | 2026-10-02T19:11:17+02:00 | n/a | `tests/unit/sdk/test_node_field_access.py::test_attribute_value_read[strict-sync-absent-on-node-with-id] PASSED` |
| `test_node_field_access.py::test_assigning_absent_attribute_makes_it_known[{warn,strict}-{standard,sync}-{attribute-value,node-attribute}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_assigning_absent_attribute_makes_it_known[warn-standard-attribute-value] PASSED` |
| `test_node_field_access.py::test_never_set_attribute_becomes_unknown_once_new_node_is_saved[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_never_set_attribute_becomes_unknown_once_new_node_is_saved[strict-standard] PASSED` |
| `test_node_field_access.py::test_related_node_accessor_reads[{warn,strict}-{standard,sync}-{present-with-peer,present-with-null-node,absent-on-node-with-id,absent-on-node-without-id}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_related_node_accessor_reads[strict-standard-absent-on-node-with-id] PASSED` |
| `test_node_field_access.py::test_related_node_peer_lookup_on_present_relationship[{warn,strict}-{standard,sync}-{get,peer}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_related_node_peer_lookup_on_present_relationship[warn-sync-peer] PASSED` |
| `test_node_field_access.py::test_related_node_peer_lookup_without_identifier[{warn,strict}-{standard,sync}-{present-with-null-node,absent-on-node-with-id,absent-on-node-without-id}-{get,peer}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_related_node_peer_lookup_without_identifier[strict-sync-absent-on-node-with-id-peer] PASSED` |
| `test_node_field_access.py::test_assigning_absent_related_node_makes_it_known[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_assigning_absent_related_node_makes_it_known[warn-standard] PASSED` |
| `test_node_field_access.py::test_hierarchical_parent_read[{warn,strict}-{standard,sync}-{present,absent-on-node-with-id}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_hierarchical_parent_read[strict-sync-absent-on-node-with-id] PASSED` |
| `test_node_field_access.py::test_relationship_manager_reads[{warn,strict}-{standard,sync}-{present-with-peer,present-with-no-edges,absent-on-node-with-id,absent-on-node-without-id}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_relationship_manager_reads[strict-standard-absent-on-node-with-id] PASSED` |
| `test_node_field_access.py::test_relationship_manager_index_on_{present,unknown}_relationship[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_relationship_manager_index_on_unknown_relationship[strict-sync] PASSED` |
| `test_node_field_access.py::test_relationship_manager_is_known_after_fetch[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_relationship_manager_is_known_after_fetch[warn-sync] PASSED` |
| `test_node_field_access.py::test_editing_unknown_relationship_manager_still_requires_fetch[{warn,strict}-{standard,sync}-{add,extend,remove}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_editing_unknown_relationship_manager_still_requires_fetch[warn-standard-add] PASSED` |
| `test_node_field_access.py::test_relationship_manager_peers_can_be_replaced_and_appended[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_relationship_manager_peers_can_be_replaced_and_appended[strict-sync] PASSED` |
| `test_node_field_access.py::test_storing_partial_node_is_silent[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_storing_partial_node_is_silent[strict-sync] PASSED` |
| `test_node_field_access.py::test_hfid_through_unknown_relationship_is_none_and_node_is_stored_by_id[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_hfid_through_unknown_relationship_is_none_and_node_is_stored_by_id[strict-standard] PASSED` |
| `test_node_field_access.py::test_update_of_partial_node_sends_only_id_and_modified_attribute[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_update_of_partial_node_sends_only_id_and_modified_attribute[strict-sync] PASSED` |
| `test_node_field_access.py::test_upsert_of_new_node_is_silent[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_upsert_of_new_node_is_silent[warn-standard] PASSED` |
| `test_node_field_access.py::test_path_value_through_unknown_fields_is_silent[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T19:11:17+02:00 | n/a | `...::test_path_value_through_unknown_fields_is_silent[strict-standard] PASSED` |
| `test_node_field_access.py::test_strict_switch_alone_turns_the_warning_of_a_fetched_node_into_the_error[{standard,sync}]` | unit | as above | 2026-10-02T20:04:11+02:00 | n/a | `tests/unit/sdk/test_node_field_access.py::test_strict_switch_alone_turns_the_warning_of_a_fetched_node_into_the_error[sync] PASSED` |
| `test_node_field_access.py::test_unknown_read_raises_on_node_with_strict_selection[{standard,sync}-{attribute,cardinality-one,cardinality-many}]` | unit | as above | 2026-10-02T20:04:11+02:00 | n/a | `...::test_unknown_read_raises_on_node_with_strict_selection[sync-cardinality-many] PASSED` |
| `test_node_field_access.py::test_unknown_read_warning_names_non_strict_selection[{standard,sync}]` | unit | as above | 2026-10-02T20:04:11+02:00 | n/a | `...::test_unknown_read_warning_names_non_strict_selection[standard] PASSED` |
| `test_node_field_access.py::test_related_node_fetch_without_a_peer_raises_before_any_read_or_request[{warn,strict}-{standard,sync}-{unknown-relationship,unknown-relationship-of-only-node,known-empty-relationship}]` | unit | as above | 2026-10-02T20:04:11+02:00 | n/a | `...::test_related_node_fetch_without_a_peer_raises_before_any_read_or_request[strict-sync-unknown-relationship] PASSED` |
| `test_node_field_access.py::test_never_set_relationship_becomes_unknown_once_new_node_is_saved[{warn,strict}-{standard,sync}]` | unit | as above | 2026-10-02T20:04:11+02:00 | n/a | `...::test_never_set_relationship_becomes_unknown_once_new_node_is_saved[warn-standard] PASSED` |
| `tests/unit/ctl/formatters/test_table.py::TestTableFormatterUnknownFields::{test_format_list_shows_unknown_fields_as_blank_cells,test_format_list_hides_unknown_field_columns_by_default,test_format_detail_shows_unknown_fields_as_blank_values}` | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `tests/unit/ctl/formatters/test_table.py::TestTableFormatterUnknownFields::test_format_list_shows_unknown_fields_as_blank_cells PASSED` |
| `tests/unit/ctl/formatters/test_csv.py::TestCsvFormatterUnknownFields::{3 tests}` | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `tests/unit/ctl/formatters/test_csv.py::TestCsvFormatterUnknownFields::test_format_detail_shows_unknown_fields_as_empty_values PASSED` |
| `tests/unit/ctl/formatters/test_json.py::TestJsonFormatterUnknownFields::{4 tests}` | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `tests/unit/ctl/formatters/test_json.py::TestJsonFormatterUnknownFields::test_format_detail_omits_unknown_fields PASSED` |
| `tests/unit/ctl/formatters/test_yaml.py::TestYamlFormatterUnknownFields::{3 tests}` | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `tests/unit/ctl/formatters/test_yaml.py::TestYamlFormatterUnknownFields::test_format_list_omits_unknown_fields PASSED` |
| `tests/unit/sdk/test_transfer_importer.py::test_remove_and_store_optional_relationships_skips_relationships_missing_from_the_export[{default-selection,default-selection-without-primary-tag,every-relationship-fetched}]` | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `...::test_remove_and_store_optional_relationships_skips_relationships_missing_from_the_export[default-selection] PASSED` |
| `tests/unit/ctl/object/test_update.py::test_update_cardinality_many_relationship_of_default_selection_node_sends_the_new_peers` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `tests/unit/ctl/object/test_update.py::test_update_cardinality_many_relationship_of_default_selection_node_sends_the_new_peers PASSED` |
| `tests/unit/sdk/test_file_object.py::TestMatchesLocalChecksum::test_raises_when_no_server_checksum[{standard,sync}]` (modified) | unit | chunk 4 command | 2026-10-02T18:22:23+02:00 | n/a | `tests/unit/sdk/test_file_object.py::TestMatchesLocalChecksum::test_raises_when_no_server_checksum[standard] PASSED` |
| `tests/unit/sdk/test_file_object.py::TestUnknownServerChecksum::{test_second_upload_on_node_created_by_the_first_uploads_again,test_matches_local_checksum_reports_no_server_checksum,test_download_skip_if_unchanged_downloads}[{standard,sync}-{warn,strict}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::TestUnknownServerChecksum::test_second_upload_on_node_created_by_the_first_uploads_again[sync-strict] PASSED` |
| `test_node_selection.py::test_only_query_shape_on_tag[{standard,sync}-{attribute,empty,hfid,floor-names}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `tests/unit/sdk/test_node_selection.py::test_only_query_shape_on_tag[standard-attribute] PASSED` |
| `test_node_selection.py::test_only_query_shape_on_location[{standard,sync}-{cardinality-one-floor,cardinality-many-floor,prefetch-cardinality-many,prefetch-cardinality-one}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_only_query_shape_on_location[sync-prefetch-cardinality-one] PASSED` |
| `test_node_selection.py::test_only_omits_unnamed_attribute_kind_many_relationship[{standard,sync}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_only_omits_unnamed_attribute_kind_many_relationship[standard] PASSED` |
| `test_node_selection.py::test_only_query_shape_on_hierarchical_kind[{standard,sync}-{not-named,not-named-with-prefetch,named-floor,named-with-prefetch}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_only_query_shape_on_hierarchical_kind[sync-named-floor] PASSED` |
| `test_node_selection.py::test_only_query_shape_on_generic_with_fragments[{standard,sync}-{generic-and-router-names,generic-relationship-and-switch-name,generic-names-only}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_only_query_shape_on_generic_with_fragments[standard-generic-and-router-names] PASSED` |
| `test_node_selection.py::test_default_query_is_unchanged[{standard,sync}-{location,tag}-{default,include,exclude,include-and-exclude}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_default_query_is_unchanged[sync-location-include-and-exclude] PASSED` |
| `test_node_selection.py::test_only_query_is_unchanged_when_schema_grows[{standard,sync}]` | unit | chunk 5 command | 2026-10-02T18:34:05+02:00 | n/a | `...::test_only_query_is_unchanged_when_schema_grows[standard] PASSED` |
| `test_node_selection.py::test_only_with_include_or_exclude_is_rejected_before_any_request[{standard,sync}-{filters,all,get}-{include,empty-include,exclude,empty-exclude,include-and-exclude}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `...::test_only_with_include_or_exclude_is_rejected_before_any_request[standard-get-empty-include] PASSED` |
| `test_node_selection.py::test_only_with_unknown_name_is_rejected_before_the_data_query[{standard,sync}-{filters,all,get}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `...::test_only_with_unknown_name_is_rejected_before_the_data_query[sync-all] PASSED` |
| `test_node_selection.py::test_only_with_implementing_kind_name_needs_fragment[{standard,sync}-{filters,all,get}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `...::test_only_with_implementing_kind_name_needs_fragment[standard-filters] PASSED` |
| `test_node_selection.py::test_reference_peer_of_another_kind_in_the_store_keeps_its_error[{standard,sync}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `...::test_reference_peer_of_another_kind_in_the_store_keeps_its_error[sync] PASSED` |
| `test_node_selection.py::test_only_with_prefetch_stores_the_peer_with_a_strict_peer_selection[{standard,sync}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `...::test_only_with_prefetch_stores_the_peer_with_a_strict_peer_selection[standard] PASSED` |
| `test_node_selection.py::{test_nodes_from_only_raise_on_unfetched_reads[{standard,sync}-{filters,all,get}],test_only_reference_peer_is_not_stored_and_points_at_hydration[{standard,sync}],test_nodes_without_only_warn_naming_their_selection[{standard,sync}-{default,exclude}]}` (updated in review) | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_nodes_from_only_raise_on_unfetched_reads[sync-get] PASSED` |
| `test_node_selection.py::{test_peer_expanded_without_only_warns_on_unknown_reads[{standard,sync}-{include,prefetch-relationships}],test_identity_only_peer_points_at_the_relationship_it_came_from[{standard,sync}],test_saving_a_node_from_only_sends_only_its_id_and_the_modified_attribute[{standard,sync}]}` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_saving_a_node_from_only_sends_only_its_id_and_the_modified_attribute[standard] PASSED` |
| `tests/unit/sdk/test_group_context.py::test_get_group_requests_member_references_only[{standard,sync}]` | unit | chunk 6 command | 2026-10-02T18:51:46+02:00 | n/a | `tests/unit/sdk/test_group_context.py::test_get_group_requests_member_references_only[standard] PASSED` |
| `tests/unit/sdk/test_client.py::{test_get_repositories,test_get_repositories_of_a_kind_without_ref_queries_its_default_fields}` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `tests/unit/sdk/test_client.py::test_get_repositories_of_a_kind_without_ref_queries_its_default_fields PASSED` |
| `tests/unit/ctl/test_generator.py::{test_looks_up_the_target_group_with_member_references_only,test_runs_a_target_kind_without_a_name_attribute,test_gives_each_member_its_own_params,test_resolves_every_declared_parameter,test_variables_given_on_the_command_line_bypass_the_group,test_does_not_run_when_the_group_is_empty}` | unit | chunk 6 command | 2026-10-02T18:52:03+02:00 | n/a | `tests/unit/ctl/test_generator.py::test_looks_up_the_target_group_with_member_references_only PASSED` |
| `test_node_hydration.py::test_related_node_fetch_with_only_queries_the_named_fields_of_the_peer_kind[{standard,sync}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `tests/unit/sdk/test_node_hydration.py::test_related_node_fetch_with_only_queries_the_named_fields_of_the_peer_kind[standard] PASSED` |
| `test_node_hydration.py::test_related_node_fetch_with_only_leaves_a_peer_of_a_kind_lacking_the_names_as_a_reference[{standard,sync}-{name,floor}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_related_node_fetch_with_only_leaves_a_peer_of_a_kind_lacking_the_names_as_a_reference[sync-floor] PASSED` |
| `test_node_hydration.py::test_manager_fetch_with_only_sends_one_query_per_peer_kind[{standard,sync}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_manager_fetch_with_only_sends_one_query_per_peer_kind[sync] PASSED` |
| `test_node_hydration.py::test_fetch_with_unknown_name_is_rejected_before_any_request[{standard,sync}-{related-node,uninitialized-manager}]` | unit | chunk 7 command | 2026-10-02T19:02:35+02:00 | n/a | `...::test_fetch_with_unknown_name_is_rejected_before_any_request[sync-uninitialized-manager] PASSED` |
| `test_node_hydration.py::test_fetch_with_only_and_exclude_is_rejected_before_any_request[{standard,sync}-{related-node,uninitialized-manager}-{exclude,empty-exclude}]` | unit | chunk 7 command | 2026-10-02T19:02:35+02:00 | n/a | `...::test_fetch_with_only_and_exclude_is_rejected_before_any_request[standard-related-node-empty-exclude] PASSED` |
| `test_node_hydration.py::test_uninitialized_manager_fetch_requeries_only_the_relationship[{standard,sync}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_uninitialized_manager_fetch_requeries_only_the_relationship[standard] PASSED` |
| `test_node_hydration.py::test_manager_fetch_without_only_keeps_the_default_selection[{standard,sync}-{no-arguments,exclude}]` | unit | chunk 7 command | 2026-10-02T19:02:35+02:00 | n/a | `...::test_manager_fetch_without_only_keeps_the_default_selection[sync-exclude] PASSED` |
| `test_node_hydration.py::test_related_node_fetch_with_exclude_queries_the_default_fields_minus_the_excluded_ones[{standard,sync}]` | unit | review-fix command | 2026-10-02T20:04:11+02:00 | n/a | `...::test_related_node_fetch_with_exclude_queries_the_default_fields_minus_the_excluded_ones[sync] PASSED` |

No E2E suite exists for this repository. Integration tests ran locally against a live server, so none were deferred.

## 5. Review Findings

Six reviewers ran: code, tests, comments, errors and types in parallel (read-only), then simplify (report-only).

| Severity | File | Summary | Disposition |
|---|---|---|---|
| Critical | `infrahub_sdk/client.py` (`get_list_repositories`) | Migrating to `only` named `ref`, which exists only on `CoreReadOnlyRepository`, so `kind="CoreRepository"` (the Infrahub server's git-sync path) raised `SelectionFieldNotFoundError`. It also made the returned public nodes strict. | ✅ Fixed (`39ec860b`): reverted to the original `include=[...]`, plus a regression test for `CoreRepository`. Spec FR-032 updated (deviation P1). |
| High | `infrahub_sdk/ctl/object/update.py` | The internal-access decorator hid an existing bug: `object update --set <many>=` sent `{"id": …}` only, while printing success. | ✅ Fixed (`ccc1fe2e`): the manager is marked initialized with an update, and the test asserts the mutation body. |
| High | `node/node.py`, `node/field_access.py` | The identity-floor hint (FR-026) was unreachable, because `peer_floor` was never `True`. | ✅ Fixed (`0e20cdb3`): `carries_identity_only` sets it for peers built from identity-only data, and the message names the relationship to `fetch()`. |
| High | `changelog/+infp-532-field-access.deprecated.md`, `guides/query_data.mdx` | `prefetch_relationships=True` was presented as a fix for reading an unfetched field. | ✅ Fixed (`a28cfb06`, `3ffe4033`). |
| Medium | `node/field_access.py` | The hint said "call fetch()" for attributes and cardinality-one relationships. | ✅ Fixed: the hint now depends on the field type. |
| Medium | `node/related_node.py` (`fetch`) | `fetch()` on an unknown relationship warned, or raised an error telling you to call `fetch()`. | ✅ Fixed: it raises `Error` naming the relationship and the fix, with no report first. |
| Medium | `node/node.py` (file objects) | `upload_if_changed`, `matches_local_checksum` and `download_file` read `checksum.value` as user reads, which violates FR-027. | ✅ Fixed: an unknown checksum is treated as "no server state", tested in warn and strict modes. |
| Medium | `node/relationship.py`, `node/related_node.py` | Hydration with `only` sent floor-only queries that put strict floor nodes into the store. | ✅ Fixed: kinds with no named fields are skipped (deviation P2). |
| Medium | client and node docstrings, guide, changelog | "Name `hfid`" implied it fills in `node.hfid`. | ✅ Fixed: the wording now says it adds the server `hfid` to the query and raw payload only. |
| Medium | tests | Missing: `RelatedNode.fetch(exclude)`, the FR-023 warn side for non-`only` peers, saving an `only` node, the never-set relationship rule. | ✅ Added (`0e20cdb3`). |
| Medium | `node/node.py` (`get_path_value`) | The public method runs fully under suppression, so a direct call on an `only` node returns `None` silently. | Deferred: it matches FR-027 as written ("path-value resolution"). Worth revisiting. |
| Medium | `node/selection.py` | `Selection` invariants (strict iff `only`, no `only` plus `include`) aren't enforced by the type. | Deferred. |
| Medium | `node/relationship.py` | The `peers` setter doesn't mark a manager initialized, so assigned peers are skipped on save. | Deferred: an existing asymmetry. The CLI path is fixed explicitly. |
| Low | `node/related_node.py` | Store-miss re-raise: `node_type` was "unknown", and the wording assumed "not fetched". | ✅ Fixed. |
| Low | several docstrings and comments | Class docstrings said "warns" only, `fetch` `Raises:` sections were incomplete, there was a jargon comment, the "full node" wording was wrong, selection helpers had no docstrings, the save claim was unqualified, and `Optional[...]` style was inconsistent. | ✅ Fixed (`a28cfb06`). |
| Low | types | Shared `is_loaded` helper, base `_owner` defaulting to `None`, `SelectionConflictError` parameter assumptions, keyword-only parameters, mutable `_selection`, shrinking the `ty` overrides. | Deferred. |
| Low | tests | Helpers imported from a test module, verbatim GraphQL string comparisons, asserting stub kwargs, fixture self-tests outside `tests/unit/meta/`, one truthiness assertion in integration, no unit test for the `ctl/check.py` lookup, no end-to-end test of the generic accept path, missing hierarchical `children` rows and broad-to-narrow store replacement. | Deferred. |
| Low | simplify (9 suggestions) | Drop a redundant conflict check in manager `fetch`, flatten `kind_only`, remove `is_generic` and the unused `include` parameter, one rule site for peer processing, an instance-method `for_peer`, a shared known-state base, `data_keys` hoisting, one restating docstring line. | Deferred (report-only by design, see §6). |

## 6. Autonomous Decisions

- **Dirty tree at preflight**: two untracked emacs ediff-merge auto-save files (`#%2Aediff-merge%2A#HRAqy9#`, `#%2Aediff-merge%2A#HsgEZ2#`) were at the repo root when the session started. I went ahead anyway: every subagent staged explicit paths only, and I checked after each chunk that they weren't committed. They are still untracked and untouched.
- **No `speckit-checkpoint-commit` skill**: commits were made with plain git, using conventional messages and the Co-Authored-By trailer.
- **Chunk splits**: US1 and US2 were each split in two, so every chunk's tests could pass inside that chunk.
- **Review mode**: the five read-only reviewers ran in parallel. `simplify` ran report-only, so the reviewed diff wasn't rewritten after review.
- **`get_list_repositories` reverted to `include`** (deviation P1). Filtering names per kind would have fixed the crash, but would still have made a public method's returned nodes strict, which breaks constitution II in 1.x.
- **An existing CLI bug was fixed** (`object update` on a cardinality-many relationship). This is beyond scope, but this branch's suppression had hidden its only symptom.
- **Hydration skips kinds lacking the named fields** (deviation P2), and the re-query of an uninitialized manager no longer populates the store. Both avoid replacing broader stored nodes.
- **Messages reworded** (deviation P3). The spec, contract, research and alignment check were updated after implementation.
- **Still awaiting maintainer confirmation from prep**: A1, where default queries keep `hfid` in the queried node's envelope.
- **Environment**: the shell exports `INFRAHUB_API_TOKEN`, which breaks 2 unrelated unit tests, so the suite was run with it unset. The 4 `tests/unit/doc_generation/test_docs_validate.py` failures come from `/bin/bash` not existing on this NixOS host. They fail identically at the base commit. `uv run invoke docs-validate` itself passes.
- **Vale**: 20 errors and 12 warnings remain in `lint-docs`. All are on lines unchanged since the base commit (mostly generated `sdk_ref` pages: "accessor", "typename", "upserted").
- **`python -W` caveat**: Python rejects `-W error::infrahub_sdk.exceptions.FieldNotLoadedWarning` ("invalid module name"). The docs recommend pytest's `-W`, `filterwarnings` or `warnings.simplefilter` instead. Research R4 and R16 mention the pytest form, which works.

## 7. Suggested Next Steps

1. Confirm or overrule the deviations: A1 (default envelope keeps `hfid`), P1 (`get_list_repositories` keeps `include`), P2 (hydration skips kinds lacking the names) and P3 (final message forms).
2. Open a PR (`opsmill-dev-pr`). The changelog fragments are `+infp-532-only.added.md`, `+infp-532-field-access.deprecated.md`, `+infp-532-call-sites.changed.md` and `+infp-532-object-update.fixed.md`.
3. Decide on the deferred review findings, especially `get_path_value` suppression, the `Selection` invariants and the `peers` setter semantics.
4. Ask first-party consumers (the Infrahub server, the Ansible collection, `infrahub-sync`) to run their suites with `pytest -W error::infrahub_sdk.exceptions.FieldNotLoadedWarning` against this release, to size the 2.0 impact.
5. Update the Notion PRD and the INFP-532 card, which still describe superseded designs.
6. Run `speckit-opsmill-extract` once the report has been reviewed.
