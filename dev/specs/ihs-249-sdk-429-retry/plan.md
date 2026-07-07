# Implementation Plan: SDK retry with backoff on HTTP 429 responses

**Branch**: `dga/feat-409-retry-ivj0i` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/ihs-249-sdk-429-retry/spec.md` (Jira IHS-249, GitHub #1124)

## Summary

Make the SDK transparently retry any request that receives HTTP 429, using jittered
exponential backoff (or the server's `Retry-After` when present, clamped to a max),
and raise a dedicated `RateLimitError` once a configurable retry budget is exhausted.
Behaviour is tunable and fully disableable through `Config`, identical across the async
and sync clients, and covers every request path where a 429 can occur — including the
multipart-upload and streaming-init paths that currently bypass the `_request` method.

Technical approach: a pure, I/O-free `RateLimitRetryHandler` owns all decision logic
(parse `Retry-After`, compute jittered/clamped backoff, decide continue-vs-exhausted).
Two thin retry drivers on the clients (`async` sleeps with `asyncio.sleep`, `sync` with
`time.sleep`) wrap the existing "send once" call sites and consult the handler. A new
`RateLimitError(Error)` carries `url`, `attempts`, and `last_retry_after`, chaining the
underlying `httpx.HTTPStatusError` as its `__cause__`.

## Technical Context

**Language/Version**: Python 3.10–3.13

**Primary Dependencies**: httpx (transport), pydantic v2 (Config via pydantic-settings `BaseSettings`); stdlib `random`, `time`, `asyncio`, `email.utils` (HTTP-date parsing), `logging`. No new dependencies.

**Storage**: N/A

**Testing**: pytest (`tests/unit/`), with a pluggable `requester` / `sync_requester` on `Config` and mocked httpx transports as prior art.

**Target Platform**: Cross-platform Python library (async + sync clients)

**Project Type**: Library (async/sync dual API) — single project layout under `infrahub_sdk/`.

**Performance Goals**: No throughput target; correctness of the delay sequence and attempt count is what matters. Waits must be observable and clamped; jitter must de-correlate concurrent clients.

**Constraints**: Must not change existing public method signatures. New behaviour must be default-on but fully disableable. A 429 that previously raised `httpx.HTTPStatusError` will now raise `RateLimitError` after exhaustion — a caller-visible change requiring a changelog callout.

**Scale/Scope**: Four additive `Config` fields, one new exception, one new pure-logic helper module, and retry drivers wired into three send sites per client (regular request, multipart, streaming-init).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md` → `dev/constitution.md`) is an
unfilled template with no ratified principles, so there are no formal gates to evaluate.
The de-facto project standards from `AGENTS.md` are treated as the applicable gates:

- **Async/sync dual pattern** — SATISFIED: every behaviour is delivered on both `InfrahubClient` and `InfrahubClientSync`, with a shared pure handler so there is one contract to reason about (FR-008).
- **Type hints on all signatures** — SATISFIED: all new functions/methods are fully typed.
- **No new dependencies** — SATISFIED: stdlib + existing httpx only.
- **Do not modify generated code (protocols.py)** — SATISFIED: no generated code touched.
- **Additive public API** — SATISFIED: four new `Config` fields + one new exception; no existing signature changes. The one behavioural break (429 → `RateLimitError`) is documented in the changelog.

No violations; Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/ihs-249-sdk-429-retry/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (public API surface)
│   ├── config.md
│   ├── rate_limit_error.md
│   └── rate_limit_retry_handler.md
├── checklists/
│   └── requirements.md  # From specify phase
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
infrahub_sdk/
├── client.py            # InfrahubClient (async) + InfrahubClientSync (sync).
│                        #   MODIFY: wire retry drivers into _request, _request_multipart,
│                        #   and _get_streaming / _get_streaming (sync) on both clients.
├── config.py            # ConfigBase / Config (pydantic-settings BaseSettings).
│                        #   MODIFY: add four rate_limit_* fields on ConfigBase.
├── exceptions.py        # Error base + subclasses.
│                        #   MODIFY: add RateLimitError(Error).
└── rate_limit.py        # NEW: RateLimitRetryHandler (pure, I/O-free decision logic).

tests/unit/
├── test_rate_limit.py           # NEW: handler unit tests (backoff, jitter, clamp, Retry-After parse).
└── sdk/
    └── test_rate_limit_retry.py # NEW: client-level tests (429→200, persistent 429→RateLimitError,
                                  #   Retry-After honouring, disabled path), parametrized async+sync.
```

**Structure Decision**: Single-project library layout. The pure handler lives in a new
`infrahub_sdk/rate_limit.py` (no I/O, unit-testable in isolation). The clients keep their
existing structure; the retry loop is added as a small driver method rather than being
inlined, so the async and sync variants stay symmetric and share the same handler instance
logic. `Config` gains fields on `ConfigBase` so both `Config` and any config subclasses inherit them.

## Key design decisions

1. **Chokepoint is not singular.** `login()`/`refresh_login()` route through `_request`, but
   `_request_multipart` and `_get_streaming` build their own `httpx.AsyncClient` and bypass
   `_request`. To satisfy FR-006 (queries, mutations, multipart, streaming, auth), the retry
   driver wraps a "send once → return response" callable and is applied at all three send sites
   on each client, not only `_request`. See research.md R1.
2. **Detection point.** `_request` and friends return the raw `httpx.Response` (callers invoke
   `raise_for_status()` later). The driver inspects `response.status_code == 429` directly, so
   no exception needs to be raised/caught to trigger a retry. On exhaustion the driver raises
   `RateLimitError`, chaining the `httpx.HTTPStatusError` produced from the final 429 response.
3. **Streaming semantics.** For `_get_streaming`, only the *initiation* (opening the stream and
   reading the response status) is retried; a 429 arrives in the response headers before body
   streaming begins, so retry-on-init is safe and matches FR-006's "streaming initiation".
4. **Sleep abstraction.** The pure handler returns a delay (float seconds); the async driver
   awaits `asyncio.sleep(delay)` and the sync driver calls `time.sleep(delay)`. The handler
   never sleeps, keeping it deterministic and unit-testable.
5. **Disabled path.** When `rate_limit_retry_enabled=False`, the driver performs exactly one
   send and returns the response untouched (no 429 inspection, no wait), preserving the exact
   pre-feature behaviour (FR-009 / SC-006).

## Complexity Tracking

> No constitution violations; table intentionally empty.
