# Contract: `Config` rate-limit fields (additive, public)

Added to `infrahub_sdk/config.py::ConfigBase`. All additive; no existing field changes.

```python
rate_limit_retry_enabled: bool = Field(
    default=True,
    description="Retry requests that receive HTTP 429 using backoff. Set False to disable.",
)
rate_limit_max_retries: int = Field(
    default=5,
    ge=0,
    description="Maximum number of retries after the initial attempt when receiving HTTP 429.",
)
rate_limit_backoff_base: float = Field(
    default=0.5,
    gt=0,
    description="Base interval in seconds for exponential backoff between 429 retries.",
)
rate_limit_backoff_max: float = Field(
    default=60.0,
    gt=0,
    description="Maximum wait in seconds for any single 429 retry (also clamps Retry-After).",
)
```

## Backward compatibility

- Purely additive; existing code constructing `Config(...)` / `InfrahubClient(...)` is unaffected.
- Environment-variable overrides follow the existing `BaseSettings` mechanism (e.g.
  `INFRAHUB_RATE_LIMIT_MAX_RETRIES`), consistent with current fields.

## Guarantees

- `rate_limit_retry_enabled=False` ⇒ a 429 is returned/raised exactly as before this feature
  (no wait, no extra attempt). (FR-009, SC-006)
- Defaults produce transparent retry for typical background workloads. (FR-001)
