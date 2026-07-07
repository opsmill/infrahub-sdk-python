# Quickstart / Validation Guide: SDK 429 retry with backoff

Validates the feature end-to-end. Assumes the repo dev setup.

## Prerequisites

```bash
uv sync --all-groups --all-extras
```

## Run the unit + client tests

```bash
uv run pytest tests/unit/test_rate_limit.py tests/unit/sdk/test_rate_limit_retry.py -v
```

## Validation scenarios (each maps to a Success Criterion)

Client-level tests use a mocked `requester` / `sync_requester` (via `Config`) or a mocked
httpx transport that returns a scripted sequence of responses.

1. **SC-001 — transparent retry-and-succeed**: script `[429, 200]`. Issue any client call.
   Expect the 200 payload returned and no exception. Assert the transport was called twice.

2. **SC-002 — honour `Retry-After`**: script a `429` carrying `Retry-After: 2` then `200`.
   Patch the driver's sleep to record its argument. Expect the recorded wait ≈ 2s (clamped to
   `rate_limit_backoff_max`). Repeat with an HTTP-date form and with `Retry-After: 0` (≈0s).

3. **SC-003 — jittered exponential backoff**: script persistent `429`. Record the sleep
   arguments. Assert each recorded wait ≤ `rate_limit_backoff_max`, the deterministic ceiling
   (`compute_backoff`) grows exponentially, and two separate runs produce different sequences.

4. **SC-004 — clean give-up**: script persistent `429` with `rate_limit_max_retries=5`.
   Expect exactly 6 transport calls and exactly one `RateLimitError`; assert `err.attempts == 6`,
   `err.url` is set, and `err.__cause__` is an `httpx.HTTPStatusError`.

5. **SC-005 — async/sync parity**: run scenarios 1–4 parametrized over `InfrahubClient` and
   `InfrahubClientSync`; assert identical attempt counts, waits (within jitter tolerance), and
   error type.

6. **SC-006 — disabled path**: set `rate_limit_retry_enabled=False`, script `[429]`. Expect the
   underlying HTTP error to surface immediately (no `RateLimitError`, no wait, single transport call).

7. **FR-006 — all request paths**: parametrize scenario 1 across a regular query/mutation
   (`_request`), a multipart upload (`_request_multipart`), and streaming initiation
   (`_get_streaming`); assert retry occurs on each.

8. **FR-007 — logging**: with `caplog`, assert a `WARNING` record per retry containing the URL,
   attempt number, and delay.

## Handler unit checks (pure, no I/O)

```bash
uv run pytest tests/unit/test_rate_limit.py -v
```

Covers: `compute_backoff` growth + clamp; `jittered_delay` range + variance; `parse_retry_after`
for delta-seconds, HTTP-date, past date (→0), and malformed (→None); `next_delay` clamping and
`Retry-After`-vs-computed selection; `should_retry` budget (`max_retries + 1` total).

## Manual smoke (optional)

Point a real client at a server that returns 429 (or a local stub), issue a bulk operation, and
observe in logs that the SDK backs off and either succeeds or raises `RateLimitError` after the
configured retries.
