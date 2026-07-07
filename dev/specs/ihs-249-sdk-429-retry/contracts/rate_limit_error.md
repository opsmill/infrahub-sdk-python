# Contract: `RateLimitError` (new public exception)

Added to `infrahub_sdk/exceptions.py`. Subclass of the base `Error`.

```python
class RateLimitError(Error):
    def __init__(
        self,
        url: str,
        attempts: int,
        retry_after: float | None = None,
        message: str | None = None,
    ) -> None:
        self.url = url
        self.attempts = attempts
        self.retry_after = retry_after
        if message is None:
            message = (
                f"Request to {url} was rate-limited (HTTP 429) after {attempts} attempt(s)."
            )
        super().__init__(message)
```

## Contract

- **Raised**: by the client retry driver when 429s persist past `rate_limit_max_retries`. (FR-005)
- **Type**: `isinstance(err, Error)` is `True` — callers catching the SDK base `Error` still catch it.
- **Distinct**: it is NOT an `httpx.HTTPStatusError`; callers can `except RateLimitError` to
  distinguish rate-limit exhaustion from other HTTP failures. (User story 6)
- **Attributes**: `url: str`, `attempts: int` (= `max_retries + 1`), `retry_after: float | None`
  (last observed `Retry-After` in seconds, `None` if never present or unparseable).
- **Cause chaining**: raised with `raise RateLimitError(...) from http_status_error`, so
  `err.__cause__` is the underlying `httpx.HTTPStatusError` built from the final 429 response.
  Callers can inspect `err.__cause__.response` for the raw response. (Open-question resolution)

## Behavioural change (changelog callout)

Before this feature, a persistent 429 surfaced as `httpx.HTTPStatusError` (via
`raise_for_status()`). With retry enabled (default), it now surfaces as `RateLimitError`
after exhaustion. Callers relying on catching `httpx.HTTPStatusError` for 429 should either
catch `RateLimitError` or inspect `__cause__`.
