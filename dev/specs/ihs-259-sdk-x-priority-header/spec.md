# Feature Specification: SDK `X-Priority` Request Header

**Feature Branch**: `dga/feat-x-priority-aa2nd`

**Created**: 2026-07-10

**Status**: Draft

**Input**: Jira IHS-259 — "feat: SDK X-Priority request header" (PRD). Related: INFP-636 (server-side prioritization, parent), GitHub #1151 (SDK feature issue), GitHub #1124 (429 retry/backoff, complementary).

## Overview

Infrahub's background systems (generators, artifacts, diffs, syncs, computed attributes) call back into the same API servers through this SDK, competing on equal footing with human/frontend traffic for a shared worker pool and database connections. Today the API layer cannot distinguish interactive from background traffic, so under heavy background load it cannot preferentially protect the frontend.

This feature gives the SDK a first-class notion of request **priority** (`high | medium | low`) that it emits as an `X-Priority` HTTP header. The originator of each request — the SDK caller — declares how important the request is, in a form the server can act on. Priority is set two ways: a **client-wide default** (a client dedicated to background work tags everything `low` with no call-site changes) and a **per-request override** on individual operations. When nothing is configured, the SDK sends no header and behaves exactly as today; the server treats absent/unknown values as `medium`, so rollout is safe and incremental.

This is the SDK's contribution to the server-side prioritization effort in INFP-636. It does **not** implement server-side admission control or 429 handling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Client-wide default priority (Priority: P1)

An operator running background workloads constructs one client with a default priority. Every request that client issues then carries `X-Priority: <value>` with no changes at any call site, so the server can shed that traffic before frontend traffic.

**Why this priority**: This is the core value of the feature — it lets an entire background workload be tagged uniformly by configuration alone, which is the dominant real-world use case (generators, syncs, `infrahubctl`, the Ansible collection). It is the minimum viable slice: shipping only this already lets operators protect frontend traffic.

**Independent Test**: Construct a client with `priority=low`, issue one request of each transport type (GraphQL query/mutation, multipart file upload, raw blob `_get`/`_post`), and assert every outgoing request carries `X-Priority: low`. Fully testable without the per-request override existing.

**Acceptance Scenarios**:

1. **Given** a client built with a default priority of `low`, **When** it issues a GraphQL query or mutation, **Then** that request carries `X-Priority: low`.
2. **Given** a client built with a default priority of `low`, **When** it issues a multipart file upload, **Then** that request carries `X-Priority: low`.
3. **Given** a client built with a default priority of `low`, **When** it issues a raw blob transfer (`_get`/`_post`), **Then** that request carries `X-Priority: low`.
4. **Given** a client built with a default priority of `medium`, **When** it issues any request, **Then** that request carries `X-Priority: medium` (an explicitly configured default is always emitted).

---

### User Story 2 - Per-request override (Priority: P2)

A caller overrides priority for a single operation on an otherwise-default client — for example, tagging one user-triggered operation `high` on a client that is otherwise dedicated to background work — without affecting any other call.

**Why this priority**: Adds targeted control on top of the client-wide default. Valuable but secondary: the default alone delivers the primary outcome, and the override is only meaningful once defaults exist.

**Independent Test**: On a client with no configured default, invoke a covered method with `priority=Priority.HIGH`, assert that one request carries `X-Priority: high`, then invoke the same method with no priority argument and assert no `X-Priority` header is present.

**Acceptance Scenarios**:

1. **Given** a client with no configured default, **When** the caller invokes a covered method with `priority=Priority.HIGH`, **Then** that one request carries `X-Priority: high`.
2. **Given** a client with no configured default, **When** the caller invokes a covered method with no priority argument, **Then** that request carries no `X-Priority` header, and a prior override does not leak into it.
3. **Given** a client with a default priority of `low`, **When** the caller invokes a covered method with `priority=Priority.HIGH`, **Then** that one request carries `X-Priority: high` and the next un-annotated call reverts to `X-Priority: low`.

---

### User Story 3 - Zero behaviour change when unconfigured (Priority: P1)

An existing SDK user who sets no priority sees no change to outgoing requests after upgrading the SDK. No `X-Priority` header is added anywhere.

**Why this priority**: Backwards compatibility is a hard safety requirement for a foundational library. It is P1 because a regression here silently changes every existing user's traffic. It is independently testable and gates safe rollout.

**Independent Test**: With a client constructed exactly as before this feature (no priority configured, no per-request argument), assert that outgoing requests across all transports contain no `X-Priority` header — identical to pre-feature behaviour.

**Acceptance Scenarios**:

1. **Given** a client with no priority configured, **When** it issues any request across any transport, **Then** no `X-Priority` header is present.
2. **Given** a client with no priority configured and a call that passes no priority argument, **When** the request is issued, **Then** the outgoing request headers are identical to pre-feature behaviour.

---

### User Story 4 - Invalid configured priority rejected loudly (Priority: P2)

An SDK developer or operator who configures an invalid priority value (a typo such as `lowe`, or any value outside the closed set) gets a loud failure at configuration-load time, not a silent malformed header on the wire.

**Why this priority**: Fail-fast on misconfiguration prevents silently shedding or over-prioritising traffic. Secondary to the happy paths but important for operational trust.

**Independent Test**: Attempt to construct configuration with an unknown priority value and assert it raises a configuration/validation error before any request is issued.

**Acceptance Scenarios**:

1. **Given** configuration with a priority value outside the closed set (e.g. `lowe`), **When** the configuration is loaded, **Then** loading fails with a validation error and no client is created.
2. **Given** configuration with a valid priority value in any letter case (e.g. `LOW`, `Low`, `low`), **When** the configuration is loaded, **Then** it is accepted and normalised to the corresponding priority.

---

### User Story 5 - Async and sync parity (Priority: P1)

A developer using the synchronous client (`InfrahubClientSync`) gets behaviour identical to the asynchronous client (`InfrahubClient`) for every aspect of this feature — configuration, defaults, per-request override, resolution, and the unconfigured no-header case.

**Why this priority**: The dual async/sync pattern is mandatory in this SDK (per AGENTS.md). Divergence would make the choice of client style silently change semantics. P1 because it is a correctness invariant across the whole feature rather than an add-on.

**Independent Test**: Run the identical assertion suite (defaults, override, omit-vs-emit, resolution) against both clients and assert identical outcomes.

**Acceptance Scenarios**:

1. **Given** the same priority configuration, **When** the assertion suite runs against `InfrahubClient` and against `InfrahubClientSync`, **Then** both produce identical outgoing `X-Priority` behaviour.

---

### Edge Cases

- **Explicit step-up on a low-default client**: a per-request `MEDIUM` on a client whose default is `low` sends `X-Priority: medium` for that call — explicit intent wins, even when stepping *up* from the default.
- **No "send no header" per-request escape once a default is set**: once a client default is configured there is no per-request way to suppress the header; the accepted equivalent is passing `MEDIUM` explicitly.
- **Batch mode and raw blob transfers**: these inherit the client default but expose **no** per-call override in v1.
- **Invalid configured value**: errors at configuration load, never at request time.
- **Caller manually pre-populates an `X-Priority` header**: only reachable via the low-level `_get`/`_post` transport methods, which accept a raw `headers=` argument (the covered public methods do not). The resolution rule is the single source of truth (documented behaviour); manually injecting the header at that low level is not a supported side channel and its interaction with resolution is not guaranteed.
- **Explicit per-request `MEDIUM` vs. no argument**: an explicit `MEDIUM` always emits `X-Priority: medium`; a `None`/absent per-request value falls through to the client default (which may itself be absent, in which case no header is sent).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a closed set of priority values `high | medium | low` as a `Priority` enum, so callers express intent as a typed value rather than a raw header string.
- **FR-002**: Users MUST be able to configure a client-wide default priority via configuration, accepting either a `Priority` enum value or a case-insensitive string (through environment or file configuration).
- **FR-003**: When a default priority is configured, System MUST attach the `X-Priority` header to **every** outgoing request across all transports — GraphQL queries/mutations, multipart uploads, and raw blob `_get`/`_post`.
- **FR-004**: When no priority is configured and none is supplied per request, System MUST omit the `X-Priority` header entirely, producing outgoing requests byte-for-byte identical to current (pre-feature) behaviour.
- **FR-005**: Users MUST be able to override priority per request via a `priority` argument (accepting a `Priority` value or `None`, default `None`) on the covered public methods: `get`, `all`, `create`, `save`, the diff methods, `execute_graphql`, and its file variant.
- **FR-006**: Priority resolution MUST be `resolved = per_request if per_request is not None else client_default`. A resolved value of `None` MUST omit the header; a resolved explicit value MUST be sent, including an explicit `MEDIUM`, which MUST send `X-Priority: medium`.
- **FR-007**: System MUST reject an invalid or unknown configured priority value at configuration-load time (a validation/type error) rather than coercing it or silently sending it.
- **FR-008**: The asynchronous client (`InfrahubClient`) and the synchronous client (`InfrahubClientSync`) MUST behave identically for every aspect of this feature.
- **FR-009**: The emitted header MUST be named exactly `X-Priority`, carrying the lowercase value string (`high`, `medium`, `low`) that corresponds to the resolved priority.

### Key Entities *(include if feature involves data)*

- **Priority** *(new)*: a closed enumeration with members `HIGH`, `MEDIUM`, `LOW`. It is the single in-code representation of request priority, owned by the SDK, with no lifecycle beyond its value. Each member maps to a lowercase wire value (`high`/`medium`/`low`).
- **Configuration** *(extended)*: gains a `priority` field defaulting to `None` (meaning "no default; omit the header"). Accepts a `Priority` value or a case-insensitive string, validated at load time.
- **Base request headers** *(extended)*: the client's base header set is extended so a configured default is injected once and rides every transport, rather than being added at each call site.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A client with a configured default emits `X-Priority: <value>` on 100% of requests, verified across GraphQL, multipart upload, and blob `_get`/`_post`.
- **SC-002**: A client with no priority configured emits no `X-Priority` header, and no other SDK-set outgoing header changes versus current behaviour (asserted by `X-Priority` being absent from the captured request; not a literal byte-for-byte comparison of transport-injected headers).
- **SC-003**: A per-request override sets the header on exactly that request and leaves the client default intact for the next call.
- **SC-004**: An invalid priority value is rejected at configuration load rather than sent or coerced.
- **SC-005**: The async and sync clients pass the identical assertion suite with identical outcomes.
- **SC-006**: A client with a configured default emits `X-Priority: <value>` on requests issued via batch mode and via raw blob transfers, confirming those transports inherit the client default (even though they expose no per-request override in v1).

## Assumptions

- **Server contract (per INFP-636)**: the header is exactly `X-Priority`; values are case-insensitive on the server; absent or unknown values are treated as `medium` server-side. This makes an absent header and a `medium` value semantically equivalent to the server, which is why omitting the header when unconfigured is safe.
- **Dual async/sync pattern is mandatory**: every change here is applied to both `InfrahubClient` and `InfrahubClientSync`, per AGENTS.md.
- **Public API signature change is accepted**: this feature adds a new enum, a new configuration field, and a new `priority` keyword argument across the covered public method surface — an intentional public-API-signature change (flagged per AGENTS.md "ask first: changing public API signatures").
- **Docs regeneration is required**: the new configuration field and docstrings require `uv run invoke docs-generate`.
- **Prior art guides implementation**: existing header handling in the client (notably `X-Infrahub-Tracker`) and current `tests/unit` client request tests are the reference for how headers are injected and asserted.

## Out of Scope

- 429 / `Retry-After` retry and backoff handling → tracked in GitHub #1124 (complementary, separate).
- Server-side admission control, dedicated-capacity routing, or database-throttle priority awareness → server side, tracked under INFP-636.
- Traffic classification guidance or auto-tagging of call sites (deciding *which* priority a given workload should use).
- Per-batch or per-blob override knobs (batch and blob transfers inherit the client default only, in v1).
- Anti-escalation enforcement (a usage guideline, not enforced in code).

## Dependencies

- **INFP-636** — server-side API Request Prioritization (parent effort that defines and consumes the `X-Priority` contract). This SDK feature is only useful once the server acts on the header, but is safe to ship independently because absent/unknown is treated as `medium`.
