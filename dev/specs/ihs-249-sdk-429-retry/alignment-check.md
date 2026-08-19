# Spec/Ask Alignment Check: SDK retry with backoff on HTTP 429 responses

**Date**: 2026-07-07
**Feature**: [spec.md](./spec.md)

## 1. Source

**Source PRD**: Jira IHS-249 — "SDK retry with backoff on HTTP 429 responses"
(`https://opsmill.atlassian.net/browse/IHS-249`), fetched via the Atlassian MCP tool.
The issue body is itself a full, structured PRD (Problem Statement, Solution Overview, 9 User
Stories, 3 prioritised User Journeys with acceptance criteria, FR-001…009, Key Entities, Edge
Cases, SC-001…005, Implementation/Testing Decisions, Out of Scope, one Open Question). Related
GitHub issue: opsmill/infrahub-sdk-python#1124. No secondary URLs to fetch.

## 2. Verdict

Result: ✅ ALIGNED

`spec.md` faithfully carries every PRD requirement, acceptance criterion, and scope boundary.
The only additions are an expansion of an existing requirement and the authorized resolution of
the PRD's explicit open question — neither is drift under the check's definition.

## 3. Findings

| Severity | Category | PRD reference | Spec reference | Description |
| ---------- | ---------- | --------------- | ---------------- | ------------- |
| ✅ none | missing | FR-001…009 | FR-001…009 | All nine functional requirements present, none dropped or softened (attempt cap, jittered+clamped backoff, Retry-After both forms, malformed fallback, RateLimitError with url/attempts/last-Retry-After, all request paths, per-retry logging, async/sync parity, tune+disable). |
| ✅ none | missing | Journeys P1–P3, User Stories 1–9 | US1–US4, Edge Cases | P1/P2/P3 journeys map to US1/US2/US3; PRD user story 8 (tune/disable) surfaced as US4. All acceptance scenarios preserved. |
| ✅ none | missing | SC-001…005 | SC-001…005 | Success criteria carried over with equivalent semantics. |
| ✅ none | contradicted | Out of Scope (503, server-side INFP-636/635, `retry_on_failure`) | Out of Scope | Scope boundaries reproduced verbatim; nothing contradicted. |
| ℹ️ info | added (authorized) | Open Question (chain httpx.HTTPStatusError as `__cause__`?) | FR-005, Assumptions | The PRD's single open question was resolved affirmatively (chain the transport error as `__cause__`). The parent prep flow explicitly authorizes autonomous clarification resolution; recorded as an assumption. Not drift. |
| ℹ️ info | added (derived) | FR-009 (disable via Config) | SC-006 | Spec adds SC-006 (disabled path raises immediately). This is a measurable expansion of FR-009, not new scope. |
| ℹ️ info | added (design) | Assumption: single `_request` chokepoint | plan.md R1 / data-model | Plan (not spec) records that multipart/streaming bypass `_request`, so retry is applied at three sites. This corrects a PRD *assumption* at the implementation layer while still satisfying FR-006; spec requirements unchanged. Not spec drift. |

No requirements are missing, no acceptance criteria dropped or softened, no requirement semantics
changed, and no off-scope scope items were introduced. The Config field defaults (enabled, 5, 0.5,
60), the new `RateLimitError`, and the additive-only API surface all match the PRD exactly.

## 4. Action

**Proceed.** No remediation passes required (remediation counter: 0). `tasks.md` is safe to hand to
the implementation phase. The affirmative resolution of the open question and the SC-006 derivation
are documented above for traceability.
