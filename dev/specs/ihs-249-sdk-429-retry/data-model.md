# Data Model: SDK retry with backoff on HTTP 429 responses

This feature is behavioural, not persistence-oriented. The "entities" are the config
fields, the pure decision helper, and the exception.

## Config fields (added to `ConfigBase`)

| Field | Type | Default | Meaning | Validation |
|-------|------|---------|---------|------------|
| `rate_limit_retry_enabled` | `bool` | `True` | Master on/off switch for 429 retry (FR-009). | — |
| `rate_limit_max_retries` | `int` | `5` | Max number of *retries* after the initial attempt; total sends = value + 1 (FR-001, SC-004). | `>= 0` |
| `rate_limit_backoff_base` | `float` | `0.5` | Base interval (seconds) for exponential backoff (FR-002). | `> 0` |
| `rate_limit_backoff_max` | `float` | `60.0` | Ceiling (seconds) for any single wait, incl. `Retry-After` (FR-002, FR-003). | `> 0` |

Notes:
- Fields live on `ConfigBase` so `Config` and any subclass inherit them.
- `rate_limit_max_retries = 0` with retry enabled means: one attempt, and a 429 immediately
  raises `RateLimitError` (0 retries) — distinct from disabled, which raises the raw error.

## `RateLimitRetryHandler` (new, pure / I/O-free) — `infrahub_sdk/rate_limit.py`

Owns all decision logic; performs no sleeping and no network I/O.

**Construction**: `RateLimitRetryHandler(max_retries: int, backoff_base: float, backoff_max: float)`.

**State**: none required beyond config values; the current attempt count is passed in per call
(keeps the handler reusable and thread/async-safe).

**Behaviour**:

| Method | Signature (conceptual) | Returns | Rules |
|--------|------------------------|---------|-------|
| `parse_retry_after` | `(header: str \| None, *, now=…) -> float \| None` | seconds, or `None` | delta-seconds → `int`; HTTP-date → `(date-now).total_seconds()` floored at 0; malformed/absent → `None` (FR-003, FR-004, past-date edge case). |
| `compute_backoff` | `(attempt: int) -> float` | ceiling seconds | `min(backoff_max, backoff_base * 2**attempt)` — the deterministic exponential ceiling (used for assertions in SC-003). |
| `jittered_delay` | `(ceiling: float) -> float` | seconds | `random.uniform(0, ceiling)` — full jitter (FR-002, SC-003). |
| `next_delay` | `(attempt: int, retry_after_header: str \| None, *, now=…) -> float` | seconds to wait | If `parse_retry_after` returns a value, use `min(it, backoff_max)`; else `jittered_delay(compute_backoff(attempt))`. All results clamped to `backoff_max`. |
| `should_retry` | `(attempts_made: int) -> bool` | bool | `attempts_made <= max_retries` (i.e. retries remain); see research R7. |

`attempt` passed to backoff is 0-indexed (first retry uses `attempt=0` → ceiling `backoff_base`).

## `RateLimitError` (new) — `infrahub_sdk/exceptions.py`

Subclass of the existing base `Error`.

| Attribute | Type | Meaning |
|-----------|------|---------|
| `url` | `str` | The request URL that kept getting rate-limited (FR-005). |
| `attempts` | `int` | Total attempts made before giving up (= `max_retries + 1`). |
| `retry_after` | `float \| None` | The last `Retry-After` value observed (parsed seconds), or `None`. |
| `message` | `str \| None` | Human-readable summary (default built from the above). |
| `__cause__` | `httpx.HTTPStatusError` | The underlying transport error, chained via `raise … from …` (open-question resolution). |

Constructor: `RateLimitError(url, attempts, retry_after=None, message=None)`.

## Retry driver (client method, not a standalone entity)

Two symmetric variants, one per client:

- Async: `await self._send_with_rate_limit_retry(send, url)` where `send` is an
  `async` callable returning `httpx.Response`; sleeps via `asyncio.sleep`.
- Sync: `self._send_with_rate_limit_retry(send, url)` where `send` is a sync callable;
  sleeps via `time.sleep`.

Loop (identical logic both variants, FR-008):

1. If `not config.rate_limit_retry_enabled` → `return send()` (single attempt, FR-009).
2. `attempts = 0`; loop: `response = send()`; `attempts += 1`.
3. If `response.status_code != 429` → return `response`.
4. If handler says no retries remain → build `httpx.HTTPStatusError` from the response and
   `raise RateLimitError(url, attempts, last_retry_after) from http_error` (FR-005).
5. Else compute `delay = handler.next_delay(attempt=attempts-1, retry_after_header=…)`,
   log `WARNING` (url, attempt, delay) (FR-007), sleep `delay`, continue.
