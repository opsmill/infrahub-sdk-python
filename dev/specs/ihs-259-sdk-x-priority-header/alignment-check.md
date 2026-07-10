# Spec / Ask Alignment Check: SDK `X-Priority` Request Header

**Date**: 2026-07-10
**Feature dir**: `specs/ihs-259-sdk-x-priority-header/`

## 1. Source

- **Source PRD**: Jira **IHS-259** — "feat: SDK X-Priority request header" (`https://opsmill.atlassian.net/browse/IHS-259`), fetched via the Atlassian integration. The Jira issue description *is* a full PRD (Problem Statement, Solution Overview, 7 User Stories, FR-001…008, Key Entities, Edge Cases, SC-001…005, Implementation/Testing Decisions, Out of Scope, Assumptions).
- Compared against: `spec.md` (current, post-critique).

## 2. Verdict

✅ **ALIGNED**

The spec faithfully carries every PRD requirement, user story, acceptance criterion, edge case, and out-of-scope boundary. The only differences are expansions of detail and testability clarifications that preserve — and in two cases make verifiable — the PRD's stated intent. No requirement is missing, changed in meaning, dropped, softened, or contradicted.

## 3. Findings

| Severity | Category | PRD reference | Spec reference | Description |
|----------|----------|---------------|----------------|-------------|
| ℹ️ Info (no drift) | mapping | PRD User Stories 1–7 | spec US1–US5 | 7 PRD stories consolidated into 5. All intent preserved: PRD US1→US1, US2 (enum) folded into FR-001 + contracts, US3 (override)→US2, US4 (rides every transport)→US1/FR-003, US5 (zero change)→US3, US6 (invalid rejected)→US4, US7 (async=sync)→US5. Consolidation, not loss. |
| ℹ️ Info (expansion) | added | PRD Assumptions ("header is exactly `X-Priority`") | spec FR-009 | Spec adds FR-009 stating the header name is exactly `X-Priority` with lowercase value. This promotes a PRD assumption to a testable requirement — expansion of detail, within PRD scope. |
| ℹ️ Info (expansion) | added | PRD Edge Cases ("batch mode and raw blob transfers inherit the client default") | spec SC-006 | Spec adds SC-006 verifying batch/blob inherit the configured default. Makes an implicit PRD scope claim testable; does not add new scope (no per-request override for these, matching the PRD). Raised by the critique (P5/X1). |
| ⚠️ Minor (clarified, not softened) | changed-wording | PRD SC-002 ("emits no `X-Priority` header — asserted byte-for-byte against current behaviour") | spec SC-002 | Reworded to "no `X-Priority` emitted; no other SDK-set outgoing header changes (assert `X-Priority` absent; not a literal byte-for-byte comparison of transport-injected headers)". The requirement (no header, no behaviour change) is unchanged; only the assertion method is clarified because httpx injects its own headers, making a literal byte comparison neither stable nor meaningful. Raised by the critique (E6). |

All FR-001…008 map 1:1 to spec FR-001…008. All SC-001, SC-003, SC-004, SC-005 map 1:1. All PRD edge cases and all five Out-of-Scope items (429/#1124, server-side/INFP-636, classification guidance, per-batch/blob knobs, anti-escalation) are present in the spec.

## 4. Action

**Proceed.** No remediation required. The spec is aligned with IHS-259; the two ⚠️/expansion items are testability clarifications that strengthen the spec without departing from the PRD. `tasks.md` (Phase 4) is ready for review and implementation.

- Remediation passes used: **0**.
