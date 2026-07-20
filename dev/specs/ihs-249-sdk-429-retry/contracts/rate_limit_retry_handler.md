# Contract: `RateLimitRetryHandler` (new, pure logic)

New module `infrahub_sdk/rate_limit.py`. No I/O, no sleeping — deterministic and unit-testable.

```python
class RateLimitRetryHandler:
    def __init__(self, max_retries: int, backoff_base: float, backoff_max: float) -> None: ...

    def parse_retry_after(
        self, header: str | None, *, now: datetime | None = None
    ) -> float | None:
        """Return seconds to wait per Retry-After, or None if absent/malformed.
        - delta-seconds: int(header)
        - HTTP-date: (parsedate_to_datetime(header) - now).total_seconds(), floored at 0
        - anything unparseable: None (caller falls back to computed backoff)."""

    def compute_backoff(self, attempt: int) -> float:
        """Deterministic exponential ceiling: min(backoff_max, backoff_base * 2**attempt)."""

    def jittered_delay(self, ceiling: float) -> float:
        """Full jitter: random.uniform(0, ceiling)."""

    def next_delay(
        self, attempt: int, retry_after_header: str | None = None, *, now: datetime | None = None
    ) -> float:
        """Honour Retry-After if parseable (clamped to backoff_max), else jittered backoff."""

    def should_retry(self, attempts_made: int) -> bool:
        """True while retries remain: attempts_made <= max_retries."""
```

## Contract guarantees (map to FR / SC)

- `compute_backoff` is monotonic non-decreasing in `attempt` and never exceeds `backoff_max`. (FR-002, SC-003)
- `jittered_delay(c)` ∈ `[0, c]`; two calls (or two handler instances) are extremely unlikely to
  match, satisfying "differ between instances". Tests assert jitter by sampling. (SC-003)
- `next_delay` clamps every result — computed *and* `Retry-After` — to `backoff_max`. (FR-003)
- `parse_retry_after` never raises on bad input; returns `None`. (FR-004)
- Past HTTP-date ⇒ `parse_retry_after` returns `0.0`, never negative. (Edge case)
- `should_retry` yields exactly `max_retries` retries ⇒ `max_retries + 1` total sends. (FR-001, SC-004)

## Determinism for tests

- `parse_retry_after`/`next_delay` accept an injectable `now` for HTTP-date tests.
- Jitter is the only nondeterministic element; tests either assert on `compute_backoff`
  (deterministic ceiling) or assert `0 <= jittered_delay(c) <= c` and that a sample of draws varies.
