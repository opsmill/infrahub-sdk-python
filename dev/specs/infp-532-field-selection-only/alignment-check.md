# Spec/Ask Alignment Check: INFP-532

**Date**: 2026-10-02

## Source

- **Primary**: the inline idea brief passed to `speckit-opsmill-auto` (grilled with the maintainer on 2026-10-02). Where it conflicts with the PRD, the brief wins.
- **Secondary**: the Notion PRD "Field Selection with only and Strict Field Access (INFP-532)", <https://app.notion.com/p/opsmill/PRD-Field-Selection-with-only-and-Strict-Field-Access-INFP-532-8fd228b83025824d9f20810f1b502f3d>, fetched in this session (last edited 2026-09-16). Used for items the brief doesn't override.

## Verdict

⚠️ **MINOR DRIFT (proceeding)**, with **one deliberate deviation that needs maintainer confirmation** (finding A1).

Every requirement, journey, success criterion, assumption, out-of-scope item and known divergence in the brief appears in `spec.md`. Requirement numbers were renumbered sequentially, and `checklists/requirements.md` maps them back to the brief. Finding A1 is a semantic change, but it's intentional. The critique (X1) showed that its premise was factually wrong. Re-running prep to restore the brief's wording would reintroduce a behaviour change for the Ansible collection's users, so this check doesn't loop on it. It's surfaced for the maintainer to confirm or overrule instead.

## Findings

| # | Severity | Category | Brief / PRD reference | Spec reference | Description |
|---|----------|----------|-----------------------|----------------|-------------|
| A1 | ⚠️ Deliberate, needs confirmation | changed | Brief FR-016 ("`hfid` is removed from the queried node's envelope only"), FR-008 ("floor names … as no-ops"), SC-004 ("except `hfid` in the queried node's envelope"), P2 scenario 4 | FR-008, FR-017, SC-004, User Story 2 scenarios 6–7, Key Entities, Out of Scope, Known Divergences | The default (no `only`) envelope keeps `hfid`. Under `only` it's left out unless named, and naming `hfid` requests it. Reason: `get_raw_graphql_data()` exposes the envelope, and the Ansible `node` module returns it to playbooks (`plugins/module_utils/node.py:37`), so the brief's "nothing reads it" premise was wrong (critique X1). The original removal is listed under Out of Scope as a separate change with consumer notice. Reverting to the brief is a one-condition change in `generate_query_data_init`. |
| A2 | Minor | changed | Brief FR-019 ("Assigning to a field the SDK doesn't know always succeeds") | FR-020 | Narrowed to attributes and cardinality-one relationships. Cardinality-many writes keep the existing `UninitializedError` contract. This matches the PRD's original FR-019 ("assigning a value to an uninitialized **attribute**") and the brief's own out-of-scope note about `add()` requiring `fetch()`. |
| A3 | Minor | added (clarification) | Brief edge case ("message should point at hydration") | FR-026 | Adds the hydration hint to the existing `NodeNotFoundError` raised when resolving a peer that was never fetched. Under the plan's store rule, that's where the brief's edge case actually surfaces (critique E1). The error type is unchanged. |
| A4 | Minor | added (clarification) | Brief FR-024a | FR-027 | Adds the CLI object update command and the JSON importer to the list of SDK-internal readers. Both are first-party readers found during research. |
| A5 | None | added (necessary) | Brief release line ("the 2.0 switch as a single flip") | FR-024, User Story 4 | Makes the single switch point an explicit, testable requirement. |
| A6 | None | cosmetic | All brief FR numbers | All FRs | Sequential renumbering, mapped in `checklists/requirements.md`. |

No requirement, goal, acceptance criterion or non-goal from the brief or PRD was dropped or softened.

## Action

Proceed to implementation with no remediation pass (counter: 0 of 2). A1 is surfaced prominently in the completion summary for the maintainer to confirm.
