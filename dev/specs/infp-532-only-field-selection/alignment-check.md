# Spec/Ask Alignment Check: Fetch Only the Named Fields with `only`

**Date**: 2026-10-14, updated 2026-10-16 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Source

The idea brief for [INFP-532](https://opsmill.atlassian.net/browse/INFP-532), pasted inline by the owner when the prep run started. It contains no links, so nothing was fetched.

The brief settles the points where these older sources differ from it, so they were not used as sources of requirements:

- the INFP-532 card, which proposes making `include` exclusive;
- the internal product review;
- the earlier PRD and the prototype branch `field-selection-only-infp-532`.

`spec.md` was compared with the brief at commit `ce2bc721`, after the critique changes.

## Verdict

⚠️ MINOR DRIFT (proceeding)

The spec carries all of the brief:

- every functional requirement (FR-001 to FR-013);
- both journeys and all their acceptance scenarios;
- every edge case and success criterion (SC-001 to SC-006);
- the constitution alignment, governance gates and assumptions;
- every out-of-scope item and follow-up.

Nothing the brief excludes was added. The differences below are clarifications made during the critique or decided by the owner afterwards. Each one resolves a case the brief leaves open or reconciles two of its statements, except the change to FR-005 on 2026-10-16, which the owner decided after a pull-request review and which replaces what the brief asked for `hfid` in `only` (owner decision 5).

## Findings

| Severity | Category | PRD reference | Spec reference | Description |
|---|---|---|---|---|
| Minor | changed | FR-001 "The query contains what FR-002 to FR-005 define, and nothing else." | FR-001; User Story 1, scenario 1 | The spec covers FR-002 to FR-007, the range the brief's SC-001 uses. It also says what "nothing else" leaves in place: filters, ordering, pagination, `count`, and the data that `property=True` and `include_metadata=True` add for the requested fields. The brief does not mention `property` or `include_metadata`. Keeping them was confirmed by the owner on 2026-10-14 (critique P7, research R4). |
| Minor | added | FR-005 | FR-005 | The spec adds that, for a generic kind, each implementing kind's HFID applies to its nodes. The brief does not cover generic kinds whose implementing kinds have their own HFID, as `Cat` does in the SDK's test schema (critique P5). Since 2026-10-16 the spec says instead that `hfid` is requested for a generic kind when the generic or an implementing kind has an HFID (owner decision 5). |
| Minor | changed | FR-002; FR-005; Out of Scope: "Using the server's `hfid` as a fallback for `node.hfid`" | FR-002, FR-005, Out of Scope | `hfid` in `only` now requests the HFID that the server stores, and a node from that query returns it as `node.hfid`. The spec no longer fetches the parts of the HFID. Out of Scope now leaves out the server's `hfid` only for nodes not from `only` and for nodes whose query did not name `hfid`. Decided by the owner on 2026-10-16 (owner decision 5). |
| Minor | changed | SC-002 | SC-002 | SC-002 now leaves out added fields that are named in `only`. As the brief wrote it, SC-002 conflicts with its own edge case for generic kinds: adding a named field to another implementing kind must add that field to the query (critique P6). |
| Minor | added | Key Entities | Key Entities, "Reading a field" | The spec defines what counts as reading a field for each field type, so FR-010 and SC-005 can be tested for relationships. This adds detail; it does not change the requirement. |
| Note | plan only | Out of Scope: "Using the server's `hfid` as a fallback for `node.hfid`" | research.md R10 | After `device.site.fetch(only=[...])`, `device.site.hfid` keeps the server value the reference carried when the fetched peer's HFID cannot be calculated. This concerns the relationship's `hfid`, not `node.hfid`. Confirmed by the owner on 2026-10-14. |
| Minor | changed | FR-006 "fetched only when named, as references" | FR-006 | Hierarchy fields named in `only` now follow FR-003 and FR-004 like other named relationships: references, or their peers' default fields with `prefetch_relationships=True`. The brief's FR-006 and FR-004 left this open. The owner chose this reading on 2026-10-14 (critique P3). |

## Owner decisions (2026-10-14)

After the first version of this report, the owner answered the four open decisions:

1. `RelatedNode.hfid` and `hfid_str` keep the reference's server value after `fetch(only=...)` when the fetched peer's HFID cannot be calculated. Confirmed as planned (research R10).
2. `property=True` and `include_metadata=True` keep adding their data for the named fields under `only`. Confirmed as planned (spec FR-001, research R4).
3. Hierarchy fields named in `only` follow FR-003 and FR-004, so `prefetch_relationships=True` gives their default fields. This reverses the plan's first reading. FR-006, research R4, R9 and R15, the contract and tasks T012, T014, T017 and T021 were updated.
4. `upload_if_changed`, `matches_local_checksum` and `download_file(skip_if_unchanged=True)` raise `FieldNotLoadedError` when `checksum` was not fetched. Confirmed as planned (research R13).

## Owner decision (2026-10-16)

5. `hfid` in `only` requests the HFID that the server stores, instead of the fields that make it up. Since Infrahub 1.5.0 the server stores each node's HFID as an attribute. When a query requests `hfid`, it returns the stored value and calculates the HFID only when no value is stored (research R5 links the server code). Requesting the parts made the server follow each relationship in the HFID and read the peer's attribute, plus the peer's own `hfid` and `display_label`, which costs more than reading the stored value and works against the purpose of `only`. Source: the [review thread](https://github.com/opsmill/infrahub-sdk-python/pull/1423#discussion_r4294381206). FR-002, FR-005, the edge cases and Out of Scope in the spec, research R4, R5, R8, R9, R10, R15 and R17, the plan, the data model, the contract and the quickstart were updated.

## Action

Proceed. No remediation pass was needed (0 of 2 used). Every open decision is settled, including the change to FR-005 that the owner decided on 2026-10-16.
