# Feature Specification: SDK retry with backoff on HTTP 429 responses

**Feature Branch**: `dga/feat-409-retry-ivj0i`

**Created**: 2026-07-07

**Status**: Draft

**Input**: Jira IHS-249 — "SDK retry with backoff on HTTP 429 responses"; GitHub issue opsmill/infrahub-sdk-python#1124

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transparent retry-and-succeed (Priority: P1)

A caller makes a request through the SDK. The server returns HTTP 429 (Too Many Requests), with or without a `Retry-After` header. The SDK waits and retries automatically; the request then succeeds and the caller receives the result with no error and no retry code of their own.

**Why this priority**: This is the core value of the feature — transient rate-limiting stops failing scripts and callers no longer need to hand-write retry loops. Without it the feature delivers nothing; with it alone the SDK is already meaningfully more resilient.

**Independent Test**: Point a client at a transport that returns one 429 then a 200, issue any request, and confirm the caller receives the 200 result with no exception raised. Fully testable in isolation and delivers immediate value.

**Acceptance Scenarios**:

1. **Given** a client whose next request will receive one 429 followed by a 200, **When** the caller issues the request, **Then** the SDK returns the 200 result transparently and the caller observes no error.
2. **Given** rate-limit retry is enabled (the default), **When** a 429 is received, **Then** the SDK waits before re-issuing the same request rather than surfacing the 429 immediately.

---

### User Story 2 - Respect `Retry-After` (Priority: P2)

When the server returns a 429 carrying a `Retry-After` header, the SDK waits the server-specified duration before retrying, parsing both the delta-seconds form (`Retry-After: 5`) and the HTTP-date form (`Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`). The wait is clamped to the configured maximum.

**Why this priority**: Honouring `Retry-After` is what lets a load-shedding server control exactly when background SDK traffic returns. It builds directly on P1 and is the cooperative-backoff contract the server-side prioritisation work (INFP-636) depends on.

**Independent Test**: Return a 429 with `Retry-After: N` (once in delta-seconds form, once in HTTP-date form) followed by a 200, and confirm the observed wait before the retry is approximately N seconds (or the configured maximum when N exceeds it).

**Acceptance Scenarios**:

1. **Given** a 429 carrying `Retry-After: N` in delta-seconds form, **When** the SDK retries, **Then** the wait before the next attempt is approximately N seconds (clamped to the configured maximum if N exceeds it).
2. **Given** a 429 carrying `Retry-After` as an HTTP-date, **When** the SDK retries, **Then** the wait before the next attempt is approximately the interval between now and that date (clamped to the maximum, and never negative).
3. **Given** a 429 whose `Retry-After` header is malformed or unparseable, **When** the SDK retries, **Then** the retry still happens using the computed exponential backoff and no error is raised over the bad header.

---

### User Story 3 - Give up cleanly on sustained rate-limiting (Priority: P3)

The server returns 429 on every attempt. After the configured maximum number of retries the SDK stops trying and raises a dedicated `RateLimitError`, having logged each attempt. The error carries enough context (the URL, the number of attempts made, and the last `Retry-After` seen) for the caller to react.

**Why this priority**: A hard cap prevents a persistently overloaded server from hanging a caller indefinitely and gives callers a clear, catchable failure distinct from other HTTP errors. It depends on P1's retry loop already existing.

**Independent Test**: Point a client at a transport that always returns 429, issue a request, and confirm exactly `max_retries + 1` attempts are made and exactly one `RateLimitError` is raised carrying the URL, attempt count, and last `Retry-After`.

**Acceptance Scenarios**:

1. **Given** a server that always returns 429, **When** the caller issues a request, **Then** exactly `max_retries + 1` total attempts are made and a single `RateLimitError` is raised.
2. **Given** retries have been exhausted, **When** the `RateLimitError` is raised, **Then** it exposes the request URL, the number of attempts made, and the last `Retry-After` value observed.
3. **Given** each retry occurs, **When** the SDK waits, **Then** it emits a log record identifying the URL, the attempt number, and the delay applied.

---

### User Story 4 - Tune or disable the behaviour (Priority: P3)

A developer whose needs differ from the defaults adjusts the retry behaviour — or turns it off entirely — through configuration, without changing any call sites.

**Why this priority**: Escape hatches matter for callers who already have their own retry strategy or who need deterministic failure. It is additive and does not block the core journeys.

**Independent Test**: Set the disable flag in configuration, return a single 429, and confirm the SDK raises immediately without retrying (matching the pre-feature behaviour path). Separately, lower the maximum-retries value and confirm the attempt count follows.

**Acceptance Scenarios**:

1. **Given** rate-limit retry is disabled via configuration, **When** a 429 is received, **Then** the SDK surfaces the error immediately with no wait and no retry.
2. **Given** the maximum retries and backoff bounds are changed via configuration, **When** a persistent 429 occurs, **Then** the observed attempt count and waits follow the configured values.
3. **Given** identical configuration, **When** the same 429 sequence is driven through the asynchronous client and the synchronous client, **Then** both produce identical observable behaviour (attempt counts, waits within jitter tolerance, and the same error type).

---

### Edge Cases

- **`Retry-After` as a past HTTP-date**: treated as a zero / minimal wait, never a negative delay.
- **`Retry-After` malformed or unparseable**: ignored; the SDK falls back to computed exponential backoff and still retries.
- **`Retry-After` larger than the configured maximum wait**: clamped down to the configured maximum.
- **429 on a mutating request (create/update/upload)**: safe to retry, because a 429 is a pre-processing rejection with no partial write on the server.
- **Many concurrent clients hitting the same 429**: jitter in the computed backoff prevents them retrying in lockstep and re-saturating the server (thundering herd).
- **Retry disabled via configuration**: a 429 raises immediately, preserving the existing behaviour path.
- **429 exhaustion**: the caller sees a `RateLimitError` rather than the raw transport error, but can still inspect the underlying HTTP error through the raised exception's cause.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The SDK MUST retry a request that receives HTTP 429, up to a configurable maximum number of attempts.
- **FR-002**: Between retries the SDK MUST wait using exponential backoff with random jitter, and MUST clamp each computed wait to a configurable maximum. Successive computed waits MUST grow until the ceiling is reached, and two client instances MUST NOT produce identical wait sequences (jitter must be present).
- **FR-003**: When a 429 response includes a `Retry-After` header, the SDK MUST honour it in place of the computed backoff, parsing both the delta-seconds form and the HTTP-date form, and MUST clamp the resulting wait to the configured maximum.
- **FR-004**: A `Retry-After` header that is malformed or unparseable MUST NOT crash the client or cause the retry to be skipped; the SDK MUST fall back to computed exponential backoff.
- **FR-005**: When retries are exhausted, the SDK MUST raise a dedicated, catchable rate-limit error that is distinct from other HTTP errors and carries the request URL, the number of attempts made, and the last `Retry-After` value observed. The error MUST preserve the underlying transport HTTP error as its cause so callers can inspect the raw response.
- **FR-006**: Retry behaviour MUST apply to every request path where a 429 can occur — including queries, mutations, multipart uploads, streaming initiation, and authentication requests.
- **FR-007**: The SDK MUST log each retry, including the request URL, the attempt number, and the delay applied.
- **FR-008**: Retry behaviour MUST be identical between the asynchronous client and the synchronous client.
- **FR-009**: Users MUST be able to tune the retry behaviour — and to disable it entirely — through configuration. When disabled, a 429 MUST surface immediately without any retry.

### Key Entities *(include if feature involves data)*

- **Rate-limit retry configuration**: the set of tunable values that govern the behaviour — whether retry is enabled, the maximum number of retries, the base backoff interval, and the maximum backoff interval. Ships with sensible defaults (enabled, five retries, half-second base, sixty-second ceiling) and is exposed through the SDK's existing configuration surface.
- **Rate-limit retry decision logic**: pure logic (no input/output) that parses `Retry-After`, computes jittered exponential backoff, clamps waits to the maximum, and decides whether to continue retrying or declare exhaustion. Consumed identically by both clients.
- **Rate-limit error**: the dedicated exception raised on exhaustion. A subtype of the SDK's base error, carrying the request URL, attempts made, and last `Retry-After` seen, with the underlying transport error preserved as its cause.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A request that receives a 429 then a success returns the successful result transparently, with no error surfaced and no caller-side retry code.
- **SC-002**: With `Retry-After: N` present, the wait before the next attempt is within jitter tolerance of N seconds, and approximately zero when the header indicates zero or a past date.
- **SC-003**: Without `Retry-After`, successive waits grow exponentially, never exceed the configured maximum, and differ between two independent client instances (demonstrating jitter).
- **SC-004**: After the configured maximum consecutive 429s, exactly one rate-limit error is raised and no further requests are attempted (total attempts equal maximum retries plus one).
- **SC-005**: The observable behaviour — attempt counts, waits within jitter tolerance, results, and error type — is identical across the asynchronous and synchronous clients.
- **SC-006**: With retry disabled through configuration, a single 429 surfaces immediately with no wait and no additional attempt.

## Assumptions

- A 429 is a pre-processing rejection by the server, so retrying any request method — including mutations and uploads — is safe and cannot cause a partial write.
- The server communicates recovery time via a standard `Retry-After` header when it chooses to; its absence is normal and handled by computed backoff.
- All 429-returning traffic flows through the clients' shared request chokepoint, so the retry loop can be applied in one place and cover every request path.
- The rate-limit error preserving the underlying transport error as its cause is the desired resolution of the PRD's open question, chosen because it is low cost and preserves the caller's ability to inspect the raw response.
- Default configuration values (enabled, five retries, half-second base backoff, sixty-second maximum backoff) are appropriate for typical background workloads and can be overridden per caller.
- The existing connectivity-level retry mechanism (`retry_on_failure`) is independent and remains unchanged; this feature does not modify or unify it.

## Out of Scope

- Retrying HTTP status codes other than 429 (for example 503).
- Server-side rate limiting, origin/priority signalling, or dedicated API capacity — those are the server-side halves of INFP-636 and INFP-635, tracked separately.
- Changing or unifying the existing connectivity `retry_on_failure` mechanism.
- Any new CLI commands or configuration surface beyond the additive rate-limit settings; `infrahubctl` inherits the behaviour transparently.
