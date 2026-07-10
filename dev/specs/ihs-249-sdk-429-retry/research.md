# Research: SDK retry with backoff on HTTP 429 responses

## R1 — Where do 429s actually surface? (chokepoint audit)

**Decision**: Apply the retry driver at three send sites per client, not only `_request`.

**Findings** (from `infrahub_sdk/client.py`):

- `_request` (async ~L1486, sync equivalent) calls `self._request_method` (default
  `_default_request_method`, overridable via `Config.requester`) and returns the raw
  `httpx.Response`. `_post`, `_get`, `login`, and `refresh_login` all funnel through
  `_request` — so **queries, mutations, and auth are covered by wrapping `_request`**.
- `_request_multipart` (async ~L1383) builds its own `httpx.AsyncClient` and calls
  `client.post(...)` directly — it **bypasses `_request`**. Must be wrapped separately
  to satisfy FR-006 (multipart uploads).
- `_get_streaming` (async ~L1455) is an `@asynccontextmanager` that opens `client.stream(...)`
  directly — it **bypasses `_request`**. Retry must wrap the *initiation* of the stream.

**Sync client is symmetric.** `InfrahubClientSync` (class @ L2053) mirrors the async client
exactly: `_request` (L3583) is the funnel for `_get`/`_post`/`login`/`refresh_login`, while
`_request_multipart` (L2343 send) and `_get_streaming` (L3545 send) each build their own
`httpx.Client` and bypass `_request`. So the same three-send-site treatment applies to **both**
clients — six send sites total.

**Exhaustive send-site audit.** Enumerating every direct httpx send in `client.py`
(`client.request` / `client.post` / `client.stream`) yields exactly six call sites — three per
client, listed above. The many `response.raise_for_status()` lines are response *consumers* that
run on responses already obtained via those send sites, not new send paths. There is therefore no
fourth path to cover on either client.

**Rationale**: The PRD assumed a single `_request` chokepoint; the code shows two additional
send paths per client. Covering all three (on each of the async and sync clients) is required for
FR-006 and FR-008. A shared retry driver — one async variant (`asyncio.sleep`) and one sync
variant (`time.sleep`), both consuming the same pure `RateLimitRetryHandler` — wraps a "perform
one send, return the response" callable so all six call sites behave identically.

**Alternatives considered**:

- *Refactor multipart/streaming to route through `_request`*: larger blast radius, changes
  more code paths, risks regressions in streaming/upload behaviour. Rejected in favour of
  wrapping each send site with the same driver.
- *Retry only `_request`*: simplest but violates FR-006 (multipart + streaming uncovered). Rejected.

## R2 — Detecting a 429 without disturbing existing error flow

**Decision**: Inspect `response.status_code == 429` on the returned response inside the driver;
do not rely on `raise_for_status()`.

**Rationale**: `_request`/`_request_multipart` return the raw response; callers call
`raise_for_status()` afterwards. Inspecting the status code directly lets the driver decide to
retry before any exception is raised, and preserves the existing behaviour for every non-429
response (returned untouched). On exhaustion the driver synthesizes the terminal error by
calling `response.raise_for_status()` (which raises `httpx.HTTPStatusError`) and chains it as
the `__cause__` of `RateLimitError`.

**Alternatives considered**: Catching `httpx.HTTPStatusError` around callers — rejected because
`_request` doesn't raise it and the catch sites are scattered.

## R3 — Backoff algorithm (FR-002, SC-003)

**Decision**: `computed = min(backoff_max, backoff_base * 2**attempt)`, then apply full jitter:
`delay = random.uniform(0, computed)`. `attempt` is 0-indexed per request.

**Rationale**: "Full jitter" (AWS Architecture Blog, *Exponential Backoff And Jitter*) minimises
thundering-herd re-saturation better than equal/decorrelated jitter for this use case, and
trivially satisfies SC-003 (two instances differ). The base×2^attempt term grows exponentially
until clamped to `backoff_max`.

**Note on SC-003 "successive waits grow exponentially"**: because full jitter samples in
`[0, computed]`, an individual sampled sequence is not monotonic. The *ceiling* (`computed`, the
upper bound) grows exponentially and is clamped; the handler exposes both the clamped ceiling and
the jittered delay so tests can assert the ceiling growth deterministically and assert jitter
presence separately. See data-model.md.

**Alternatives considered**: Equal jitter (`computed/2 + uniform(0, computed/2)`) — also valid;
full jitter chosen for maximum de-correlation. `random.random()`-based — equivalent, `uniform`
is clearer.

## R4 — Parsing `Retry-After` (FR-003, FR-004, edge cases)

**Decision**: Support both RFC 7231 forms; on any parse failure fall back to computed backoff.

- **delta-seconds**: `int(value)` → seconds.
- **HTTP-date**: `email.utils.parsedate_to_datetime(value)` (stdlib), then
  `(parsed - now).total_seconds()`, floored at `0` (past dates → 0, never negative).
- **Malformed / unparseable** (non-numeric, bad date, empty): return `None` → driver uses
  computed backoff (FR-004).
- Result is clamped to `backoff_max` in all cases (FR-003).

**Rationale**: `email.utils.parsedate_to_datetime` is stdlib and handles RFC-compliant HTTP-dates
(it returns timezone-aware datetimes for GMT). Flooring at 0 handles the past-date edge case.

**"now" injection**: to keep the handler pure/testable, the HTTP-date branch takes an injectable
`now` callable (defaults to `datetime.now(timezone.utc)`); tests pass a fixed `now`.

**Alternatives considered**: `dateutil` — rejected (new dependency). Hand-rolled date parsing —
rejected (error-prone).

## R5 — Config surface (FR-009)

**Decision**: Add four fields to `ConfigBase` (so both `Config` and subclasses inherit) using
pydantic `Field` with descriptions, matching the existing `retry_delay` / `retry_on_failure` style:

- `rate_limit_retry_enabled: bool = True`
- `rate_limit_max_retries: int = 5`
- `rate_limit_backoff_base: float = 0.5`
- `rate_limit_backoff_max: float = 60.0`

**Rationale**: `ConfigBase` (`infrahub_sdk/config.py:38`) already holds `retry_delay`,
`retry_on_failure`, `max_retry_duration`, `timeout` — the rate-limit knobs belong alongside them.
They are independent of the existing `retry_on_failure` mechanism (which is not modified — out of scope).

**Alternatives considered**: A nested `rate_limit` sub-model — rejected as heavier than the flat
style already used; four flat fields match repo convention and keep env-var mapping simple.

## R6 — `RateLimitError` shape (FR-005)

**Decision**: `class RateLimitError(Error)` with
`__init__(self, url: str, attempts: int, retry_after: float | None = None, message: str | None = None)`.
Stores `url`, `attempts`, `retry_after`; builds a default message if none given. Raised with
`raise RateLimitError(...) from http_status_error` so `__cause__` is the underlying
`httpx.HTTPStatusError` (open-question resolution).

**Rationale**: Mirrors existing `Error` subclasses in `exceptions.py` (e.g. `JsonDecodeError`
carries `url`). Chaining via `from` preserves the raw response for callers (SC / assumptions).

## R7 — Attempt accounting (FR-001, P3/SC-004)

**Decision**: `max_retries` counts *retries*, so total sends = `max_retries + 1` (one initial +
N retries). The handler decides "exhausted" when the number of retries already performed equals
`max_retries`.

**Rationale**: Matches the PRD's P3 acceptance ("exactly `max_retries + 1` attempts") and SC-004.

## R8 — Logging (FR-007)

**Decision**: The driver logs one record per retry via the SDK's existing module logger,
including URL, attempt number (1-based), and the computed/honoured delay. Level: `WARNING`
(rate-limiting is an operational condition worth surfacing) — consistent with observable-but-
non-fatal events.

**Rationale**: FR-007 requires each retry be observable. Using the existing logger keeps it
configurable by the host application.

**Log-content constraint (critique E4)**: retry log records MUST contain only the request URL,
the attempt number, and the applied delay — never request headers or payload. The login and
token-refresh paths carry `Authorization: Bearer …` headers and username/password payloads, so
broadening the log content would leak credentials. Tests assert the presence of URL/attempt/delay;
implementation must not add headers/body to the record.

## R9 — Build vs buy (critique P3)

**Decision**: Implement a small custom handler rather than adopt a retry library.

**Rationale**:

- **httpx transport-level `retries`** (`httpx.HTTPTransport(retries=N)`) retries only connection
  establishment failures, not HTTP status codes — it cannot see a 429, so it cannot satisfy FR-001/003.
- **`tenacity`** would be a new runtime dependency, which is out of scope ("no new dependency"),
  and would still need custom predicates for 429 detection, `Retry-After` parsing, and the
  `RateLimitError` contract — most of the logic we'd write anyway.
- The required logic (parse `Retry-After`, jittered/clamped backoff, attempt budget) is small,
  pure, and fully unit-testable with stdlib only.

**Alternatives considered**: `tenacity`, `backoff`, httpx transport retries — all rejected for the
reasons above.
