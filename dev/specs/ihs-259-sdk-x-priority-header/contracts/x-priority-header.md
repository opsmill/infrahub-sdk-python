# Wire Contract: `X-Priority` HTTP header

**Feature**: IHS-259 | **Consumer**: Infrahub API server (INFP-636)

## Header

| Property | Value |
|----------|-------|
| Name | `X-Priority` (exact, case-insensitive on the server per HTTP header rules) |
| Values | `high`, `medium`, `low` (lowercase emitted by the SDK) |
| Cardinality | 0 or 1 per request |

## Emission rules (SDK side)

1. The SDK emits the header on a request **iff** the resolved priority for that request is non-`None`.
2. When emitted, the value is exactly the lowercase token of the resolved `Priority` member.
3. The header is emitted uniformly across every transport when a client-wide default is configured: GraphQL query/mutation, multipart file upload, and raw blob `_get`/`_post`.
4. When no priority is configured and none is passed per request, the header is **absent** — the outgoing request is byte-for-byte identical to the pre-feature SDK.

## Server semantics (assumed, per INFP-636 — not implemented here)

- The server treats the value case-insensitively.
- An **absent** header and an **unknown** value are both treated as `medium`.
- Consequently, "omit the header" and "send `medium`" are server-equivalent, which is what makes omitting-when-unconfigured a safe, non-breaking rollout.

## Non-goals (this contract)

- No `Retry-After` / 429 semantics (GitHub #1124).
- No server-side admission control, routing, or throttling behaviour (INFP-636).
- The SDK does not read or react to any response header related to priority.
